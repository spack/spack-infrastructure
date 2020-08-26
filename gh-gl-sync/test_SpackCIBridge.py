import json
import os
from unittest.mock import patch

import SpackCIBridge


def test_list_github_prs(capfd):
    """Test the list_github_prs method."""
    bridge = SpackCIBridge.SpackCIBridge()
    bridge.get_prs_from_github_api = lambda *args: None
    bridge.github_pr_responses = [
        {
            "number": 1,
            "head": {
                "ref": "improve_docs",
            }
        },
        {
            "number": 2,
            "head": {
                "ref": "fix_test",
            }
        },
    ]
    assert bridge.list_github_prs("open") == ["pr1_improve_docs", "pr2_fix_test"]
    out, err = capfd.readouterr()
    assert out == "Open PRs:\n    pr1_improve_docs\n    pr2_fix_test\n"


def test_get_synced_prs(capfd):
    """Test the get_synced_prs method."""
    bridge = SpackCIBridge.SpackCIBridge()
    bridge.fetch_gitlab_prs = lambda *args: None
    bridge.gitlab_pr_output = b"""
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa	refs/heads/github/pr1_example
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb	refs/heads/github/pr2_another_try
    """
    assert bridge.get_synced_prs() == ["pr1_example", "pr2_another_try"]
    out, err = capfd.readouterr()
    assert out == "Synced PRs:\n    pr1_example\n    pr2_another_try\n"


def test_get_prs_to_delete(capfd):
    """Test the get_prs_to_delete method."""
    open_prs = ["pr3_try_this", "pr4_new_stuff"]
    synced_prs = ["pr1_first_try", "pr2_different_approach", "pr3_try_this"]
    bridge = SpackCIBridge.SpackCIBridge()
    closed_refspecs = bridge.get_prs_to_delete(open_prs, synced_prs)
    assert closed_refspecs == [":github/pr1_first_try", ":github/pr2_different_approach"]
    out, err = capfd.readouterr()
    assert out == "Synced Closed PRs:\n    pr1_first_try\n    pr2_different_approach\n"


def test_get_open_refspecs():
    """Test the get_open_refspecs method."""
    open_prs = ["pr1_this", "pr2_that"]
    bridge = SpackCIBridge.SpackCIBridge()
    open_refspecs, fetch_refspecs = bridge.get_open_refspecs(open_prs)
    assert open_refspecs == [
        "github/pr1_this:github/pr1_this",
        "github/pr2_that:github/pr2_that"
    ]
    assert fetch_refspecs == [
        "+refs/pull/1/head:refs/remotes/github/pr1_this",
        "+refs/pull/2/head:refs/remotes/github/pr2_that"
    ]


def test_ssh_agent():
    """Test starting & stopping ssh-agent."""
    def check_pid(pid):
        """Local function to check if a PID is running or not."""
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    # Read in our private key.
    # Don't worry, this key was just generated for testing.
    # It's not actually used for anything.
    key_file = open("test_key.base64", "r")
    ssh_key_base64 = key_file.read()
    key_file.close()

    # Start ssh-agent.
    bridge = SpackCIBridge.SpackCIBridge()
    bridge.setup_ssh(ssh_key_base64)

    assert "SSH_AGENT_PID" in os.environ
    pid = int(os.environ["SSH_AGENT_PID"])
    assert check_pid(pid)

    # Run our cleanup function to kill the ssh-agent.
    SpackCIBridge.SpackCIBridge.cleanup()

    # Make sure it's not running any more.
    # The loop/sleep is to give the process a little time to shut down.
    import time
    for i in range(10):
        if check_pid(pid):
            time.sleep(0.01)
    assert not check_pid(pid)

    # Prevent atexit from trying to kill it again.
    del os.environ["SSH_AGENT_PID"]


def test_get_pipeline_api_template():
    """Test the get_pipeline_api_template method."""
    bridge = SpackCIBridge.SpackCIBridge()
    template = bridge.get_pipeline_api_template("ssh.gitlab.spack.io", "zack/my_test_proj")
    assert template == "https://gitlab.spack.io/api/v4/projects/zack%2Fmy_test_proj/pipelines?ref={0}"


def test_dedupe_pipelines():
    """Test the dedupe_pipelines method."""
    input = [
        {
            "id": 1,
            "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ref": "github/pr1_readme",
            "status": "failed",
            "created_at": "2020-08-26T17:26:30.216Z",
            "updated_at": "2020-08-26T17:26:36.807Z",
            "web_url": "https://gitlab.spack.io/zack/my_test_proj/pipelines/1"
        },
        {
            "id": 2,
            "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ref": "github/pr1_readme",
            "status": "passed",
            "created_at": "2020-08-27T17:27:30.216Z",
            "updated_at": "2020-08-27T17:27:36.807Z",
            "web_url": "https://gitlab.spack.io/zack/my_test_proj/pipelines/2"
        },
        {
            "id": 3,
            "sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "ref": "github/pr2_todo",
            "status": "failed",
            "created_at": "2020-08-26T17:26:30.216Z",
            "updated_at": "2020-08-26T17:26:36.807Z",
            "web_url": "https://gitlab.spack.io/zack/my_test_proj/pipelines/3"
        },
    ]
    expected = {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {
            "id": 2,
            "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ref": "github/pr1_readme",
            "status": "passed",
            "created_at": "2020-08-27T17:27:30.216Z",
            "updated_at": "2020-08-27T17:27:36.807Z",
            "web_url": "https://gitlab.spack.io/zack/my_test_proj/pipelines/2"
        },
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": {
            "id": 3,
            "sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "ref": "github/pr2_todo",
            "status": "failed",
            "created_at": "2020-08-26T17:26:30.216Z",
            "updated_at": "2020-08-26T17:26:36.807Z",
            "web_url": "https://gitlab.spack.io/zack/my_test_proj/pipelines/3"
        },
    }
    bridge = SpackCIBridge.SpackCIBridge()
    assert bridge.dedupe_pipelines(input) == expected


def test_make_status_for_pipeline():
    """Test the make_status_for_pipeline method."""
    bridge = SpackCIBridge.SpackCIBridge()
    pipeline = {"web_url": "foo"}
    status = bridge.make_status_for_pipeline(pipeline)
    assert status == {}

    test_cases = [
        {
            "input": "created",
            "state": "pending",
            "description": "Pipeline has been created",
        },
        {
            "input": "waiting_for_resource",
            "state": "pending",
            "description": "Pipeline is waiting for resources",
        },
        {
            "input": "preparing",
            "state": "pending",
            "description": "Pipeline is preparing",
        },
        {
            "input": "pending",
            "state": "pending",
            "description": "Pipeline is pending",
        },
        {
            "input": "running",
            "state": "pending",
            "description": "Pipeline is running",
        },
        {
            "input": "manual",
            "state": "pending",
            "description": "Pipeline is running manually",
        },
        {
            "input": "scheduled",
            "state": "pending",
            "description": "Pipeline is scheduled",
        },
        {
            "input": "failed",
            "state": "error",
            "description": "Pipeline failed",
        },
        {
            "input": "canceled",
            "state": "failure",
            "description": "Pipeline was canceled",
        },
        {
            "input": "skipped",
            "state": "failure",
            "description": "Pipeline was skipped",
        },
        {
            "input": "success",
            "state": "success",
            "description": "Pipeline succeeded",
        },
    ]
    for test_case in test_cases:
        pipeline["status"] = test_case["input"]
        status = bridge.make_status_for_pipeline(pipeline)
        assert json.loads(status.decode("utf-8"))["state"] == test_case["state"]
        assert json.loads(status.decode("utf-8"))["description"] == test_case["description"]


class FakeResponse:
    status: int
    data: bytes

    def __init__(self, *, data: bytes):
        self.data = data

    def read(self):
        self.status = 201 if self.data is not None else 404
        return self.data

    def close(self):
        pass


def test_post_pipeline_status(capfd):
    """Test the post_pipeline_status method."""
    open_prs = ["pr1_readme"]
    template = "https://gitlab.spack.io/api/v4/projects/zack%2Fmy_test_proj/pipelines?ref={0}"
    bridge = SpackCIBridge.SpackCIBridge()
    bridge.github_repo = "zack/my_test_proj"
    os.environ["GITHUB_TOKEN"] = "my_github_token"
    mock_data = b'''[
        {
            "id": 1,
            "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ref": "github/pr1_readme",
            "status": "failed",
            "created_at": "2020-08-26T17:26:30.216Z",
            "updated_at": "2020-08-26T17:26:36.807Z",
            "web_url": "https://gitlab.spack.io/zack/my_test_proj/pipelines/1"
        }
    ]'''
    with patch('urllib.request.urlopen', return_value=FakeResponse(data=mock_data)) as mock_urlopen:
        bridge.post_pipeline_status(open_prs, template)
        assert mock_urlopen.call_count == 2
    out, err = capfd.readouterr()
    assert out == "Posting status for pr1_readme / aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    del os.environ["GITHUB_TOKEN"]
