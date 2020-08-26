#!/usr/bin/env python3

import argparse
import atexit
import base64
import dateutil.parser
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
        self.gitlab_url = ""
        self.github_url = ""

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
        pr_strings = []
        self.get_prs_from_github_api(state)
        for self.github_pr_response in self.github_pr_responses:
            pr_string = "pr{0}_{1}".format(self.github_pr_response["number"], self.github_pr_response["head"]["ref"])
            pr_strings.append(pr_string)
        pr_strings = sorted(pr_strings)
        print("{0} PRs:".format(state.capitalize()))
        for pr_string in pr_strings:
            print("    {0}".format(pr_string))
        return pr_strings

    def get_prs_from_github_api(self, state):
        """Query the GitHub API for PRs with a given state: open, closed, or all.
        Store this retrieved data in self.github_pr_responses.
        """
        self.github_pr_responses = []
        try:
            request = urllib.request.Request(
                    "https://api.github.com/repos/%s/pulls?state=%s" % (self.github_repo, state))
            request.add_header("Authorization", "token %s" % os.environ["GITHUB_TOKEN"])
            response = urllib.request.urlopen(request)
        except OSError:
            return
        self.github_pr_responses = json.loads(response.read())

    def setup_git_repo(self):
        """Initialize a bare git repository with two remotes:
        one for GitHub and one for GitLab.
        """
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "remote", "add", "github", self.github_url], check=True)
        subprocess.run(["git", "remote", "add", "gitlab", self.gitlab_url], check=True)

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
        pr_number_regexp = re.compile(r"pr([0-9]+)")
        open_refspecs = []
        fetch_refspecs = []
        for open_pr in open_prs:
            match = pr_number_regexp.search(open_pr)
            if match is None:
                continue
            pr_num = match.group(1)
            fetch_refspecs.append("+refs/pull/{0}/head:refs/remotes/github/{1}".format(pr_num, open_pr))
            open_refspecs.append("github/{0}:github/{0}".format(open_pr))
        return open_refspecs, fetch_refspecs

    def fetch_github_prs(self, fetch_refspecs):
        """Perform `git fetch` for a given list of refspecs."""
        print("Fetching GitHub refs for open PRs")
        fetch_args = ["git", "fetch", "-q", "github"] + fetch_refspecs
        subprocess.run(fetch_args, check=True)

    def build_local_branches(self, open_prs):
        """Create local branches for a list of open PRs."""
        print("Building local branches for open PRs")
        for open_pr in open_prs:
            branch_name = "github/{0}".format(open_pr)
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

        post_data = json.dumps(post_data).encode('utf-8')
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

    def get_pipeline_api_template(self, gitlab_host, gitlab_repo):
        template = gitlab_host.replace("ssh.", "https://")
        template += "/api/v4/projects/"
        template += urllib.parse.quote_plus(gitlab_repo)
        template += "/pipelines?ref={0}"
        return template

    def post_pipeline_status(self, open_prs, pipeline_api_template):
        for open_pr in open_prs:
            # Use gitlab's API to get pipeline results for the corresponding ref.
            api_url = pipeline_api_template.format("github/" + open_pr)
            try:
                request = urllib.request.Request(api_url)
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
                print("Posting status for {0} / {1}".format(open_pr, sha))
                post_data = self.make_status_for_pipeline(pipeline)
                post_request = urllib.request.Request(
                        "https://api.github.com/repos/{0}/statuses/{1}".format(self.github_repo, sha),
                        data=post_data)
                post_request.add_header("Authorization", "token %s" % os.environ["GITHUB_TOKEN"])
                post_request.add_header("Accept", "application/vnd.github.v3+json")
                post_response = urllib.request.urlopen(post_request)
                if post_response.status != 201:
                    print("Expected 201 when creating status, got {0}".format(post_response.status))

    def sync(self, args):
        """Synchronize pull requests from GitHub as branches on GitLab."""
        # Handle input arguments for connecting to GitHub and GitLab.
        os.environ["GIT_SSH_COMMAND"] = "ssh -F /dev/null -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
        self.gitlab_url = "git@{0}:{1}.git".format(args.gitlab_host, args.gitlab_repo)
        self.github_url = "https://github.com/{0}.git".format(args.github_repo)
        self.github_repo = args.github_repo

        # Work inside a temporary directory that will be deleted when this script terminates.
        with tempfile.TemporaryDirectory() as tmpdirname:
            os.chdir(tmpdirname)

            # Setup the local repo with two remotes.
            self.setup_git_repo()

            # Retrieve currently open PRs from GitHub.
            open_prs = self.list_github_prs("open")

            # Retrieve PRs that have already been synced to GitLab.
            synced_prs = self.get_synced_prs()

            # Find closed PRs that are currently synced.
            # These will be deleted from GitLab.
            closed_refspecs = self.get_prs_to_delete(open_prs, synced_prs)

            # Get refspecs for open PRs.
            open_refspecs, fetch_refspecs = self.get_open_refspecs(open_prs)

            # Sync open GitHub PRs to GitLab.
            self.fetch_github_prs(fetch_refspecs)
            self.build_local_branches(open_prs)
            if open_refspecs or closed_refspecs:
                print("Syncing PRs to GitLab")
                push_args = ["git", "push", "--porcelain", "-f", "gitlab"] + closed_refspecs + open_refspecs
                subprocess.run(push_args, check=True)

            # Post pipeline status to GitHub for each open PR.
            pipeline_api_template = self.get_pipeline_api_template(args.gitlab_host, args.gitlab_repo)
            self.post_pipeline_status(open_prs, pipeline_api_template)


if __name__ == "__main__":
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Sync GitHub PRs to GitLab")
    parser.add_argument("github_repo", help="GitHub repo (org/repo or user/repo)")
    parser.add_argument("gitlab_host", help="URL to GitLab server")
    parser.add_argument("gitlab_repo", help="GitLab repo (org/repo or user/repo)")

    args = parser.parse_args()

    ssh_key_base64 = os.getenv("GITLAB_SSH_KEY_BASE64")
    if ssh_key_base64 is None:
        raise Exception("GITLAB_SSH_KEY_BASE64 environment is not set")

    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    bridge = SpackCIBridge()
    bridge.setup_ssh(ssh_key_base64)
    bridge.sync(args)
