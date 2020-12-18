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

    def __init__(self):
        self.gitlab_repo = ""
        self.github_repo = ""
        self.github_project = ""
        self.unmergeable_shas = []

        self.py_github = Github(os.environ.get('GITHUB_TOKEN'))
        self.py_gh_repo = self.py_github.get_repo('spack/spack', lazy=True)

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

    def list_github_prs(self, state):
        """ Return a list of strings in the format: "pr<PR#>_<headref>"
        for GitHub PRs with a given state: open, closed, or all.
        """
        pr_dict = {}
        pulls = self.py_gh_repo.get_pulls(state=state)
        for pull in pulls:
            if not pull.merge_commit_sha:
                print("PR {0} ({1}) has no 'merge_commit_sha', skipping".format(pull.number, pull.head.ref))
                self.unmergeable_shas.append(pull.head.sha)
                continue
            pr_string = "pr{0}_{1}".format(pull.number, pull.head.ref)
            pr_dict[pr_string] = pull.merge_commit_sha

        pr_strings = sorted(pr_dict.keys())
        merge_commit_shas = [pr_dict[s] for s in pr_strings]
        print("{0} PRs:".format(state.capitalize()))
        for pr_string in pr_strings:
            print("    {0}".format(pr_string))
        return {
            "pr_strings": pr_strings,
            "merge_commit_shas": merge_commit_shas,
        }

    def list_github_protected_branches(self):
        """ Return a list of protected branch names from GitHub."""
        branches = self.py_gh_repo.get_branches()
        protected_branches = [br.name for br in branches if br.protected]
        protected_branches = sorted(protected_branches)
        print("Protected branches:")
        for protected_branch in protected_branches:
            print("    {0}".format(protected_branch))
        return protected_branches

    def list_github_tags(self):
        """ Return a list of tag names from GitHub."""
        tag_list = self.py_gh_repo.get_tags()
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

    def fetch_gitlab_prs(self):
        """Query GitLab for branches that have already been copied over from GitHub PRs.
        Return the string output of `git ls-remote`.
        """
        ls_remote_args = ["git", "ls-remote", "gitlab", "github/pr*"]
        self.gitlab_pr_output = \
            subprocess.run(ls_remote_args, check=True, stdout=subprocess.PIPE).stdout

    def get_synced_prs(self):
        """Return a list of PRs that have already been synchronized to GitLab."""
        self.fetch_gitlab_prs()
        synced_prs = []
        for line in self.gitlab_pr_output.split(b"\n"):
            parts = line.split()
            if len(parts) != 2:
                continue
            synced_pr = parts[1].replace(b"refs/heads/github/", b"").decode("utf-8")
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
        pr_strings = open_prs["pr_strings"]
        merge_commit_shas = open_prs["merge_commit_shas"]
        open_refspecs = []
        fetch_refspecs = []
        for open_pr, merge_commit_sha in zip(pr_strings, merge_commit_shas):
            fetch_refspecs.append("+{0}:refs/remotes/github/{1}".format(
                merge_commit_sha, open_pr))
            open_refspecs.append("github/{0}:github/{0}".format(open_pr))
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
            post_data["state"] = "failure"
            post_data["description"] = "Pipeline was canceled"

        elif pipeline["status"] == "skipped":
            post_data["state"] = "failure"
            post_data["description"] = "Pipeline was skipped"

        elif pipeline["status"] == "success":
            post_data["state"] = "success"
            post_data["description"] = "Pipeline succeeded"

        post_data["target_url"] = pipeline["web_url"]
        post_data["context"] = "ci/gitlab-ci"
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

    def get_pipeline_api_template(self, gitlab_host, gitlab_project):
        dt = datetime.now(timezone.utc) + timedelta(minutes=-4)
        time_threshold = urllib.parse.quote_plus(dt.isoformat(timespec="seconds"))
        template = gitlab_host
        template += "/api/v4/projects/"
        template += urllib.parse.quote_plus(gitlab_project)
        template += "/pipelines?updated_after={0}".format(time_threshold)
        template += "&ref={0}"
        return template

    def post_pipeline_status(self, branches, pipeline_api_template):
        for branch in branches:
            # Use gitlab's API to get pipeline results for the corresponding ref.
            api_url = pipeline_api_template.format("github/" + branch)
            try:
                request = urllib.request.Request(api_url)
                if "GITLAB_TOKEN" in os.environ:
                    request.add_header("Authorization", "Bearer %s" % os.environ["GITLAB_TOKEN"])
                response = urllib.request.urlopen(request)
            except OSError:
                continue
            try:
                pipelines = json.loads(response.read())
            except json.decoder.JSONDecodeError:
                continue
            # Post status to GitHub for each pipeline found.
            pipelines = self.dedupe_pipelines(pipelines)
            for sha, pipeline in pipelines.items():
                print("Posting status for {0} / {1}".format(branch, sha))
                post_data = self.make_status_for_pipeline(pipeline)
                status_response = self.py_gh_repo.get_commit(sha=sha).create_status(
                    state=post_data["state"],
                    target_url=post_data["target_url"],
                    description=post_data["description"],
                    context=post_data["context"]
                )
                if status_response.state != post_data["state"]:
                    print("Expected CommitStatus state {0}, got {1}".format(
                        post_data["state"], status_response.state))

        # Post errors to any PRs that we found didn't have a merge_commit_sha, and
        # thus were likely unmergeable.
        for sha in self.unmergeable_shas:
            commit_state = "error"
            status_response = self.py_gh_repo.get_commit(sha=sha).create_status(
                state=commit_state,
                description="PR could not be merged with base",
                context="ci/gitlab-ci"
            )
            if status_response.state != commit_state:
                print("Expected CommitStatus state {0}, got {1}".format(
                    commit_state, status_response.state))

    def delete_pr_mirrors(self, closed_refspecs):
        if closed_refspecs:
            bucket_name = "spack-pr-mirrors"

            s3 = boto3.resource("s3")
            bucket = s3.Bucket(bucket_name)

            print("Deleting mirrors for closed PRs:")
            for refspec in closed_refspecs:
                pr_mirror_key = refspec[1:]
                print("    deleting {0}".format(pr_mirror_key))
                bucket.objects.filter(Prefix=pr_mirror_key).delete()

    def sync(self, args):
        """Synchronize pull requests from GitHub as branches on GitLab."""
        # Handle input arguments for connecting to GitHub and GitLab.
        os.environ["GIT_SSH_COMMAND"] = "ssh -F /dev/null -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
        self.gitlab_repo = args.gitlab_repo
        self.github_repo = "https://{0}@github.com/{1}.git".format(os.environ["GITHUB_TOKEN"], args.github_project)
        self.github_project = args.github_project
        self.unmergeable_shas = []
        post_status = not args.disable_status_post

        # Work inside a temporary directory that will be deleted when this script terminates.
        with tempfile.TemporaryDirectory() as tmpdirname:
            os.chdir(tmpdirname)

            # Setup the local repo with two remotes.
            self.setup_git_repo()

            # Retrieve currently open PRs from GitHub.
            open_prs = self.list_github_prs("open")

            # # Get protected branches on GitHub.
            protected_branches = self.list_github_protected_branches()

            # Get tags on GitHub.
            tags = self.list_github_tags()

            # Retrieve PRs that have already been synced to GitLab.
            synced_prs = self.get_synced_prs()

            # Find closed PRs that are currently synced.
            # These will be deleted from GitLab.
            closed_refspecs = self.get_prs_to_delete(open_prs["pr_strings"], synced_prs)

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
            if "AWS_ACCESS_KEY_ID" in os.environ and "AWS_SECRET_ACCESS_KEY" in os.environ:
                self.delete_pr_mirrors(closed_refspecs)

            # Post pipeline status to GitHub for each open PR, if enabled
            if post_status:
                pipeline_api_template = self.get_pipeline_api_template(args.gitlab_host, args.gitlab_project)
                self.post_pipeline_status(open_prs["pr_strings"] + protected_branches, pipeline_api_template)


if __name__ == "__main__":
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Sync GitHub PRs to GitLab")
    parser.add_argument("github_project", help="GitHub project (org/repo or user/repo)")
    parser.add_argument("gitlab_repo", help="Full clone URL for GitLab")
    parser.add_argument("gitlab_host", help="GitLab web host")
    parser.add_argument("gitlab_project", help="GitLab project (org/repo or user/repo)")
    parser.add_argument("--disable-status-post", action="store_true", default=False,
                        help="Do not post pipeline status to each GitHub PR")

    args = parser.parse_args()

    ssh_key_base64 = os.getenv("GITLAB_SSH_KEY_BASE64")
    if ssh_key_base64 is None:
        raise Exception("GITLAB_SSH_KEY_BASE64 environment is not set")

    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    bridge = SpackCIBridge()
    bridge.setup_ssh(ssh_key_base64)
    bridge.sync(args)
