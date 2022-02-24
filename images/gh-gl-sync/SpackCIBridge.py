#!/usr/bin/env python3

import argparse
import atexit
import base64
import boto3
from datetime import datetime, timedelta, timezone
import dateutil.parser
from github import Github
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request


class SpackCIBridge(object):

    def __init__(self, gitlab_repo="", gitlab_host="", gitlab_project="", github_project="",
                 disable_status_post=True, pr_mirror_bucket=None, main_branch=None, prereq_checks=[]):
        self.gitlab_repo = gitlab_repo
        self.github_project = github_project
        github_token = os.environ.get('GITHUB_TOKEN')
        self.github_repo = "https://{0}@github.com/{1}.git".format(github_token, self.github_project)
        self.py_github = Github(github_token)
        self.py_gh_repo = self.py_github.get_repo(self.github_project, lazy=True)

        self.merge_msg_regex = re.compile(r"Merge\s+([^\s]+)\s+into\s+[^\s]+")
        self.unmergeable_shas = []

        self.post_status = not disable_status_post
        self.pr_mirror_bucket = pr_mirror_bucket
        self.main_branch = main_branch
        self.currently_running_sha = None
        self.currently_running_url = None

        self.prereq_checks = prereq_checks

        dt = datetime.now(timezone.utc) + timedelta(minutes=-60)
        self.time_threshold_brief = urllib.parse.quote_plus(dt.isoformat(timespec="seconds"))

        # We use a longer time threshold to find the currently running main branch pipeline.
        dt = datetime.now(timezone.utc) + timedelta(minutes=-1440)
        self.time_threshold_long = urllib.parse.quote_plus(dt.isoformat(timespec="seconds"))

        self.pipeline_api_template = gitlab_host
        self.pipeline_api_template += "/api/v4/projects/"
        self.pipeline_api_template += urllib.parse.quote_plus(gitlab_project)
        self.pipeline_api_template += "/pipelines?updated_after={0}"
        self.pipeline_api_template += "&ref={1}"

        self.commit_api_template = gitlab_host
        self.commit_api_template += "/api/v4/projects/"
        self.commit_api_template += urllib.parse.quote_plus(gitlab_project)
        self.commit_api_template += "/repository/commits/{0}"

        self.cached_commits = {}

    @atexit.register
    def cleanup():
        """Shutdown ssh-agent upon program termination."""
        if "SSH_AGENT_PID" in os.environ:
            print("    Shutting down ssh-agent({0})".format(os.environ["SSH_AGENT_PID"]))
            subprocess.run(["ssh-agent", "-k"], check=True)

    def setup_ssh(self, ssh_key_base64):
        """Start the ssh agent."""
        print("Starting ssh-agent")
        output = subprocess.run(["ssh-agent", "-s"], check=True, stdout=subprocess.PIPE).stdout

        # Search for PID in output.
        pid_regexp = re.compile(r"SSH_AGENT_PID=([0-9]+)")
        match = pid_regexp.search(output.decode("utf-8"))
        if match is None:
            print("WARNING: could not detect ssh-agent PID.", file=sys.stderr)
            print("ssh-agent will not be killed upon program termination", file=sys.stderr)
        else:
            pid = match.group(1)
            os.environ["SSH_AGENT_PID"] = pid
            self.cleanup_ssh_agent = True

        # Search for socket in output.
        socket_regexp = re.compile(r"SSH_AUTH_SOCK=([^;]+);")
        match = socket_regexp.search(output.decode("utf-8"))
        if match is None:
            print("WARNING: could not detect ssh-agent socket.", file=sys.stderr)
            print("Key will be added to caller's ssh-agent (if any)", file=sys.stderr)
        else:
            socket = match.group(1)
            os.environ["SSH_AUTH_SOCK"] = socket

        # Add the key.
        ssh_key = base64.b64decode(ssh_key_base64)
        ssh_key = ssh_key.replace(b"\r", b"")
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(ssh_key)
            fp.seek(0)
            subprocess.run(["ssh-add", fp.name], check=True)

    def get_commit(self, commit):
        """ Check our cache for a commit on GitHub.
            If we don't have it yet, use the GitHub API to retrieve it."""
        if commit not in self.cached_commits:
            self.cached_commits[commit] = self.py_gh_repo.get_commit(sha=commit)
        return self.cached_commits[commit]

    def list_github_prs(self):
        """ Return two dicts of data about open PRs on GitHub:
            one for all open PRs, and one for open PRs that are not up-to-date on GitLab."""
        pr_dict = {}
        pulls = self.py_gh_repo.get_pulls(state="open")
        print("Rate limit after get_pulls(): {}".format(self.py_github.rate_limiting[0]))
        for pull in pulls:
            if pull.draft:
                print("Skipping draft PR {0} ({1})".format(pull.number, pull.head.ref))
                continue
            if not pull.merge_commit_sha:
                print("PR {0} ({1}) has no 'merge_commit_sha', skipping".format(pull.number, pull.head.ref))
                self.unmergeable_shas.append(pull.head.sha)
                continue
            pr_string = "pr{0}_{1}".format(pull.number, pull.head.ref)

            # Determine what PRs need to be pushed to GitLab. This happens in one of two cases:
            # 1) we have never pushed it before
            # 2) we have pushed it before, but the HEAD sha has changed since we pushed it last
            push = True
            log_args = ["git", "log", "--pretty=%s", "gitlab/github/{0}".format(pr_string)]
            try:
                merge_commit_msg = subprocess.run(
                    log_args, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
                match = self.merge_msg_regex.match(merge_commit_msg.decode("utf-8"))
                if match and match.group(1) == pull.head.sha:
                    print("Skip pushing {0} because GitLab already has HEAD {1}".format(pr_string, pull.head.sha))
                    push = False

            except subprocess.CalledProcessError:
                # This occurs when it's a new PR that hasn't been pushed to GitLab yet.
                pass

            backlogged = False
            if push:
                # Check the PRs-to-be-pushed to see if any of them should be considered "backlogged".
                # We currently recognize two types of backlogged PRs:
                # 1) The PR is based on a version of the "main branch" that's currently being tested
                # 2) Some required "prerequisite checks" have not yet completed successfully.
                if self.currently_running_sha and self.currently_running_sha == pull.base.sha:
                    backlogged = "base"
                if self.prereq_checks:
                    checks_desc = "waiting for {} check to succeed"
                    checks_to_verify = self.prereq_checks.copy()
                    pr_check_runs = self.get_commit(pull.head.sha).get_check_runs()
                    for check in pr_check_runs:
                        if check.name in checks_to_verify:
                            checks_to_verify.remove(check.name)
                            if check.conclusion != "success":
                                backlogged = checks_desc.format(check.name)
                                break
                    if not backlogged and checks_to_verify:
                        backlogged = checks_desc.format(checks_to_verify[0])

            pr_dict[pr_string] = {
                'merge_commit_sha': pull.merge_commit_sha,
                'base_sha': pull.base.sha,
                'head_sha': pull.head.sha,
                'push': push,
                'backlogged': backlogged,
            }

        def listify_dict(d):
            pr_strings = sorted(d.keys())
            merge_commit_shas = [d[s]['merge_commit_sha'] for s in pr_strings]
            base_shas = [d[s]['base_sha'] for s in pr_strings]
            head_shas = [d[s]['head_sha'] for s in pr_strings]
            b_logged = [d[s]['backlogged'] for s in pr_strings]
            return {
                "pr_strings": pr_strings,
                "merge_commit_shas": merge_commit_shas,
                "base_shas": base_shas,
                "head_shas": head_shas,
                "backlogged": b_logged,
            }
        all_open_prs = listify_dict(pr_dict)
        filtered_pr_dict = {k: v for (k, v) in pr_dict.items() if v['push']}
        filtered_open_prs = listify_dict(filtered_pr_dict)
        print("All Open PRs:")
        for pr_string in all_open_prs['pr_strings']:
            print("    {0}".format(pr_string))
        print("Filtered Open PRs:")
        for pr_string in filtered_open_prs['pr_strings']:
            print("    {0}".format(pr_string))
        print("Rate limit at the end of list_github_prs(): {}".format(self.py_github.rate_limiting[0]))
        return [all_open_prs, filtered_open_prs]

    def list_github_protected_branches(self):
        """ Return a list of protected branch names from GitHub."""
        branches = self.py_gh_repo.get_branches()
        print("Rate limit after get_branches(): {}".format(self.py_github.rate_limiting[0]))
        protected_branches = [br.name for br in branches if br.protected]
        protected_branches = sorted(protected_branches)
        if self.currently_running_sha:
            print("Skip pushing {0} because it already has a pipeline running ({1})"
                  .format(self.main_branch, self.currently_running_sha))
            protected_branches.remove(self.main_branch)
        print("Protected branches:")
        for protected_branch in protected_branches:
            print("    {0}".format(protected_branch))
        return protected_branches

    def list_github_tags(self):
        """ Return a list of tag names from GitHub."""
        tag_list = self.py_gh_repo.get_tags()
        print("Rate limit after get_tags(): {}".format(self.py_github.rate_limiting[0]))
        tags = sorted([tag.name for tag in tag_list])
        print("Tags:")
        for tag in tags:
            print("    {0}".format(tag))
        return tags

    def setup_git_repo(self):
        """Initialize a bare git repository with two remotes:
        one for GitHub and one for GitLab.
        """
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "remote", "add", "github", self.github_repo], check=True)
        subprocess.run(["git", "remote", "add", "gitlab", self.gitlab_repo], check=True)

    def get_gitlab_pr_branches(self):
        """Query GitLab for branches that have already been copied over from GitHub PRs.
        Return the string output of `git branch --remotes --list gitlab/github/pr*`.
        """
        branch_args = ["git", "branch", "--remotes", "--list", "gitlab/github/pr*"]
        self.gitlab_pr_output = \
            subprocess.run(branch_args, check=True, stdout=subprocess.PIPE).stdout

    def gitlab_shallow_fetch(self):
        """Perform a shallow fetch from GitLab"""
        fetch_args = ["git", "fetch", "-q", "--depth=1", "gitlab"]
        subprocess.run(fetch_args, check=True, stdout=subprocess.PIPE).stdout

    def get_synced_prs(self):
        """Return a list of PR branches that already exist on GitLab."""
        self.get_gitlab_pr_branches()
        synced_prs = []
        for line in self.gitlab_pr_output.split(b"\n"):
            if line.find(b"gitlab/github/") == -1:
                continue
            synced_pr = line.strip().replace(b"gitlab/github/", b"").decode("utf-8")
            synced_prs.append(synced_pr)
        print("Synced PRs:")
        for pr in synced_prs:
            print("    {0}".format(pr))
        return synced_prs

    def get_prs_to_delete(self, open_prs, synced_prs):
        """Find PRs that have already been synchronized to GitLab that are no longer open on GitHub.
        Return a list of strings in the format of ":github/<branch_name" that will be used
        to delete these branches from GitLab.
        """
        prs_to_delete = []
        for synced_pr in synced_prs:
            if synced_pr not in open_prs:
                prs_to_delete.append(synced_pr)
        print("Synced Closed PRs:")
        closed_refspecs = []
        for pr in prs_to_delete:
            print("    {0}".format(pr))
            closed_refspecs.append(":github/{0}".format(pr))
        return closed_refspecs

    def get_open_refspecs(self, open_prs):
        """Return lists of refspecs for fetch and push given a list of open PRs."""
        print("Building initial lists of refspecs to fetch and push")
        pr_strings = open_prs["pr_strings"]
        merge_commit_shas = open_prs["merge_commit_shas"]
        base_shas = open_prs["base_shas"]
        backlogged = open_prs["backlogged"]
        open_refspecs = []
        fetch_refspecs = []
        for open_pr, merge_commit_sha, base_sha, backlog in zip(pr_strings,
                                                                merge_commit_shas,
                                                                base_shas,
                                                                backlogged):
            fetch_refspecs.append("+{0}:refs/remotes/github/{1}".format(
                merge_commit_sha, open_pr))
            if not backlog:
                open_refspecs.append("github/{0}:github/{0}".format(open_pr))
                print("  pushing {0} (based on {1})".format(open_pr, base_sha))
            else:
                if backlog == "base":
                    # By omitting these branches from "open_refspecs", we will defer pushing
                    # them to gitlab for a time when there is not a main branch pipeline running
                    # on one of their parent commits.
                    print("  defer pushing {0} (based on {1})".format(open_pr, base_sha))
                else:
                    print("  defer pushing {0} (based on checks)".format(open_pr))
        return open_refspecs, fetch_refspecs

    def update_refspecs_for_protected_branches(self, protected_branches, open_refspecs, fetch_refspecs):
        """Update our refspecs lists for protected branches from GitHub."""
        for protected_branch in protected_branches:
            fetch_refspecs.append("+refs/heads/{0}:refs/remotes/github/{0}".format(protected_branch))
            open_refspecs.append("github/{0}:github/{0}".format(protected_branch))
        return open_refspecs, fetch_refspecs

    def update_refspecs_for_tags(self, tags, open_refspecs, fetch_refspecs):
        """Update our refspecs lists for tags from GitHub."""
        for tag in tags:
            fetch_refspecs.append("+refs/tags/{0}:refs/tags/{0}".format(tag))
            open_refspecs.append("refs/tags/{0}:refs/tags/{0}".format(tag))
        return open_refspecs, fetch_refspecs

    def fetch_github_branches(self, fetch_refspecs):
        """Perform `git fetch` for a given list of refspecs."""
        print("Fetching GitHub refs for open PRs")
        fetch_args = ["git", "fetch", "-q", "github"] + fetch_refspecs
        subprocess.run(fetch_args, check=True)

    def build_local_branches(self, open_prs, protected_branches):
        """Create local branches for a list of open PRs and protected branches."""
        print("Building local branches for open PRs and protected branches")
        for branch in open_prs["pr_strings"] + protected_branches:
            branch_name = "github/{0}".format(branch)
            subprocess.run(["git", "branch", "-q", branch_name, branch_name], check=True)

    def make_status_for_pipeline(self, pipeline):
        """Generate POST data to create a GitHub status from a GitLab pipeline
           API response
        """
        post_data = {}
        if "status" not in pipeline:
            return post_data

        if pipeline["status"] == "created":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline has been created"

        elif pipeline["status"] == "waiting_for_resource":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline is waiting for resources"

        elif pipeline["status"] == "preparing":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline is preparing"

        elif pipeline["status"] == "pending":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline is pending"

        elif pipeline["status"] == "running":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline is running"

        elif pipeline["status"] == "manual":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline is running manually"

        elif pipeline["status"] == "scheduled":
            post_data["state"] = "pending"
            post_data["description"] = "Pipeline is scheduled"

        elif pipeline["status"] == "failed":
            post_data["state"] = "error"
            post_data["description"] = "Pipeline failed"

        elif pipeline["status"] == "canceled":
            # Do not post canceled pipeline status to GitHub, it's confusing to our users.
            # This usually happens when a PR gets force-pushed. The next time the sync script runs
            # it will post a status for the newly force-pushed commit.
            return {}

        elif pipeline["status"] == "skipped":
            post_data["state"] = "failure"
            post_data["description"] = "Pipeline was skipped"

        elif pipeline["status"] == "success":
            post_data["state"] = "success"
            post_data["description"] = "Pipeline succeeded"

        post_data["target_url"] = pipeline["web_url"]
        return post_data

    def dedupe_pipelines(self, api_response):
        """Prune pipelines API response to only include the most recent result for each SHA"""
        pipelines = {}
        for response in api_response:
            sha = response['sha']
            if sha not in pipelines:
                pipelines[sha] = response
            else:
                existing_datetime = dateutil.parser.parse(pipelines[sha]['updated_at'])
                current_datetime = dateutil.parser.parse(response['updated_at'])
                if current_datetime > existing_datetime:
                    pipelines[sha] = response
        return pipelines

    def find_pr_sha(self, tested_sha):
        api_url = self.commit_api_template.format(tested_sha)

        try:
            request = urllib.request.Request(api_url)
            if "GITLAB_TOKEN" in os.environ:
                request.add_header("Authorization", "Bearer %s" % os.environ["GITLAB_TOKEN"])
            response = urllib.request.urlopen(request)
        except OSError:
            print('Failed to fetch commit for tested sha {0}'.format(tested_sha))
            return None

        response_data = response.read()

        try:
            tested_commit_info = json.loads(response_data)
        except json.decoder.JSONDecodeError:
            print('Failed to parse response as json ({0})'.format(response_data))
            return None

        if 'title' not in tested_commit_info:
            print('Returned commit object missing "Title" field')
            return None

        merge_commit_msg = tested_commit_info['title']
        m = self.merge_msg_regex.match(merge_commit_msg)

        if m is None:
            print('Failed to find pr_sha in merge commit message')
            return None

        return m.group(1)

    def get_pipelines_for_branch(self, branch, time_threshold):
        # Use gitlab's API to get pipeline results for the corresponding ref.
        api_url = self.pipeline_api_template.format(
            time_threshold,
            urllib.parse.quote_plus("github/" + branch)
        )
        try:
            request = urllib.request.Request(api_url)
            if "GITLAB_TOKEN" in os.environ:
                request.add_header("Authorization", "Bearer %s" % os.environ["GITLAB_TOKEN"])
            response = urllib.request.urlopen(request)
        except OSError as inst:
            print("GitLab API request error accessing {0}".format(api_url))
            print(inst)
            return None
        try:
            pipelines = json.loads(response.read())
        except json.decoder.JSONDecodeError as inst:
            print("Error parsing response to {0}".format(api_url))
            print(inst)
            return None

        return self.dedupe_pipelines(pipelines)

    def post_pipeline_status(self, open_prs, protected_branches):
        print("Rate limit at the beginning of post_pipeline_status(): {}".format(self.py_github.rate_limiting[0]))
        pipeline_branches = []
        backlog_branches = []
        # Split up the open_prs branches into two piles: branches we force-pushed to gitlab
        # and branches we deferred pushing.
        for pr_branch, base_sha, head_sha, backlog in zip(open_prs["pr_strings"],
                                                          open_prs["base_shas"],
                                                          open_prs["head_shas"],
                                                          open_prs["backlogged"]):
            if not backlog:
                pipeline_branches.append(pr_branch)
            else:
                backlog_branches.append((pr_branch, head_sha, backlog))

        pipeline_branches.extend(protected_branches)

        print('Querying pipelines to post status for:')
        for branch in pipeline_branches:
            # Post status to GitHub for each pipeline found.
            pipelines = self.get_pipelines_for_branch(branch, self.time_threshold_brief)
            if not pipelines:
                continue
            for sha, pipeline in pipelines.items():
                post_data = self.make_status_for_pipeline(pipeline)
                if not post_data:
                    continue
                # TODO: associate shas with protected branches, so we do not have to
                # hit an endpoint here, but just use the sha we already know just like
                # we do below for backlogged PR statuses.
                pr_sha = self.find_pr_sha(sha)
                if not pr_sha:
                    print('Could not find github PR sha for tested commit: {0}'.format(sha))
                    print('Using tested commit to post status')
                    pr_sha = sha
                self.create_status_for_commit(pr_sha,
                                              branch,
                                              post_data["state"],
                                              post_data["target_url"],
                                              post_data["description"])

        # Post a status of pending/backlogged for branches we deferred pushing
        print('Posting backlogged status to the following:')
        base_backlog_desc = \
            "waiting for base {} commit pipeline to succeed".format(self.main_branch)
        for branch, head_sha, reason in backlog_branches:
            if reason == "base":
                desc = base_backlog_desc
                url = self.currently_running_url
            else:
                desc = reason
                url = ""
            self.create_status_for_commit(head_sha, branch, "pending", url, desc)

        # Post errors to any PRs that we found didn't have a merge_commit_sha, and
        # thus were likely unmergeable.
        print('Posting unmergeable status to the following:')
        for sha in self.unmergeable_shas:
            print('  {0}'.format(sha))
            self.create_status_for_commit(sha, "", "error", "", "PR could not be merged with base")
        print("Rate limit at the end of post_pipeline_status(): {}".format(self.py_github.rate_limiting[0]))

    def create_status_for_commit(self, sha, branch, state, target_url, description):
        context = "ci/gitlab-ci"
        commit = self.get_commit(sha)
        existing_statuses = commit.get_combined_status()
        for status in existing_statuses.statuses:
            if (status.context == context and
                    status.state == state and
                    status.description == description and
                    status.target_url == target_url):
                print("Not posting duplicate status to {} / {}".format(branch, sha))
                return
        try:
            status_response = self.get_commit(sha).create_status(
                state=state,
                target_url=target_url,
                description=description,
                context=context
            )
            if status_response.state != state:
                print("Expected CommitStatus state {0}, got {1}".format(
                    state, status_response.state))
        except Exception as e_inst:
            print('Caught exception posting status for {0}/{1}'.format(branch, sha))
            print(e_inst)
        print("  {0} -> {1}".format(branch, sha))

    def delete_pr_mirrors(self, closed_refspecs):
        if closed_refspecs:
            s3 = boto3.resource("s3")
            bucket = s3.Bucket(self.pr_mirror_bucket)

            print("Deleting mirrors for closed PRs:")
            for refspec in closed_refspecs:
                pr_mirror_key = refspec[1:]
                print("    deleting {0}".format(pr_mirror_key))
                bucket.objects.filter(Prefix=pr_mirror_key).delete()

    def sync(self):
        """Synchronize pull requests from GitHub as branches on GitLab."""

        print("Initial rate limit: {}".format(self.py_github.rate_limiting[0]))

        # Setup SSH command for communicating with GitLab.
        os.environ["GIT_SSH_COMMAND"] = "ssh -F /dev/null -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

        # Work inside a temporary directory that will be deleted when this script terminates.
        with tempfile.TemporaryDirectory() as tmpdirname:
            os.chdir(tmpdirname)

            # Setup the local repo with two remotes.
            self.setup_git_repo()

            if self.main_branch:
                # Find the currently running main branch pipeline, if any, and get the sha
                main_branch_pipelines = self.get_pipelines_for_branch(self.main_branch, self.time_threshold_long)
                for sha, pipeline in main_branch_pipelines.items():
                    if pipeline['status'] == "running":
                        self.currently_running_sha = sha
                        self.currently_running_url = pipeline["web_url"]
                        break

            print("Currently running {0} pipeline: {1}".format(self.main_branch, self.currently_running_sha))

            # Shallow fetch from GitLab.
            self.gitlab_shallow_fetch()

            # Retrieve open PRs from GitHub.
            all_open_prs, open_prs = self.list_github_prs()

            # Get protected branches on GitHub.
            protected_branches = self.list_github_protected_branches()

            # Get tags on GitHub.
            tags = self.list_github_tags()

            # Retrieve PRs that have already been synced to GitLab.
            synced_prs = self.get_synced_prs()

            # Find closed PRs that are currently synced.
            # These will be deleted from GitLab.
            closed_refspecs = self.get_prs_to_delete(all_open_prs["pr_strings"], synced_prs)

            # Get refspecs for open PRs and protected branches.
            open_refspecs, fetch_refspecs = self.get_open_refspecs(open_prs)
            self.update_refspecs_for_protected_branches(protected_branches, open_refspecs, fetch_refspecs)
            self.update_refspecs_for_tags(tags, open_refspecs, fetch_refspecs)

            # Sync open GitHub PRs and protected branches to GitLab.
            self.fetch_github_branches(fetch_refspecs)
            self.build_local_branches(open_prs, protected_branches)
            if open_refspecs or closed_refspecs:
                print("Syncing to GitLab")
                push_args = ["git", "push", "--porcelain", "-f", "gitlab"] + closed_refspecs + open_refspecs
                subprocess.run(push_args, check=True)

            # Clean up per-PR dedicated mirrors for any closed PRs
            if self.pr_mirror_bucket:
                print('Cleaning up per-PR mirrors for closed PRs')
                self.delete_pr_mirrors(closed_refspecs)

            # Post pipeline status to GitHub for each open PR, if enabled
            if self.post_status:
                print('Posting pipeline status for open PRs and protected branches')
                self.post_pipeline_status(all_open_prs, protected_branches)


if __name__ == "__main__":
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Sync GitHub PRs to GitLab")
    parser.add_argument("github_project", help="GitHub project (org/repo or user/repo)")
    parser.add_argument("gitlab_repo", help="Full clone URL for GitLab")
    parser.add_argument("gitlab_host", help="GitLab web host")
    parser.add_argument("gitlab_project", help="GitLab project (org/repo or user/repo)")
    parser.add_argument("--disable-status-post", action="store_true", default=False,
                        help="Do not post pipeline status to each GitHub PR")
    parser.add_argument("--pr-mirror-bucket", default=None,
                        help="Delete mirrors for closed PRs from the specified S3 bucket")
    parser.add_argument("--main-branch", default=None,
                        help="""If provided, we find the sha of the currently running
pipeline on this branch, and then PR branch merge commits having that sha as a parent
(base.sha) will not be synced.""")
    parser.add_argument("--prereq-check", nargs="+", default=False,
                        help="Only push branches that have already passed this GitHub check")

    args = parser.parse_args()

    ssh_key_base64 = os.getenv("GITLAB_SSH_KEY_BASE64")
    if ssh_key_base64 is None:
        raise Exception("GITLAB_SSH_KEY_BASE64 environment is not set")

    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    bridge = SpackCIBridge(gitlab_repo=args.gitlab_repo,
                           gitlab_host=args.gitlab_host,
                           gitlab_project=args.gitlab_project,
                           github_project=args.github_project,
                           disable_status_post=args.disable_status_post,
                           pr_mirror_bucket=args.pr_mirror_bucket,
                           main_branch=args.main_branch,
                           prereq_checks=args.prereq_check)
    bridge.setup_ssh(ssh_key_base64)
    bridge.sync()
