import os
from unittest.mock import patch, Mock

import SpackCIBridge


class AttrDict(dict):
    def __init__(self, iterable, **kwargs):
        super(AttrDict, self).__init__(iterable, **kwargs)
        for key, value in iterable.items():
            if isinstance(value, dict):
                self.__dict__[key] = AttrDict(value)
            else:
                self.__dict__[key] = value


def test_list_github_prs(capfd):
    """Test the list_github_prs method."""
    github_pr_response = [
        AttrDict({
            "number": 1,
            "merge_commit_sha": "aaaaaaaa",
            "head": {
                "ref": "improve_docs",
            }
        }),
        AttrDict({
            "number": 2,
            "merge_commit_sha": "bbbbbbbb",
            "head": {
                "ref": "fix_test",
            }
        }),
    ]
    gh_repo = Mock()
    gh_repo.get_pulls.return_value = github_pr_response
    bridge = SpackCIBridge.SpackCIBridge()
    bridge.py_gh_repo = gh_repo
    github_prs = bridge.list_github_prs("open")
    assert github_prs["pr_strings"] == ["pr1_improve_docs", "pr2_fix_test"]
    assert github_prs["merge_commit_shas"] == ["aaaaaaaa", "bbbbbbbb"]
    assert gh_repo.get_pulls.call_count == 1
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
    """Test the get_open_refspecs and update_refspecs_for_protected_branches methods."""
    open_prs = {
        "pr_strings": ["pr1_this", "pr2_that"],
        "merge_commit_shas": ["aaaaaaaa", "bbbbbbbb"],
    }
    bridge = SpackCIBridge.SpackCIBridge()
    open_refspecs, fetch_refspecs = bridge.get_open_refspecs(open_prs)
    assert open_refspecs == [
        "github/pr1_this:github/pr1_this",
        "github/pr2_that:github/pr2_that"
    ]
    assert fetch_refspecs == [
        "+aaaaaaaa:refs/remotes/github/pr1_this",
        "+bbbbbbbb:refs/remotes/github/pr2_that"
    ]

    protected_branches = ["develop", "master"]
    bridge.update_refspecs_for_protected_branches(protected_branches, open_refspecs, fetch_refspecs)
    assert open_refspecs == [
        "github/pr1_this:github/pr1_this",
        "github/pr2_that:github/pr2_that",
        "github/develop:github/develop",
        "github/master:github/master",
    ]
    assert fetch_refspecs == [
        "+aaaaaaaa:refs/remotes/github/pr1_this",
        "+bbbbbbbb:refs/remotes/github/pr2_that",
        "+refs/heads/develop:refs/remotes/github/develop",
        "+refs/heads/master:refs/remotes/github/master"
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
    """Test that pipeline_api_template get constructed properly."""
    bridge = SpackCIBridge.SpackCIBridge(gitlab_host="https://gitlab.spack.io", gitlab_project="zack/my_test_proj")
    template = bridge.pipeline_api_template
    assert template[0:84] == "https://gitlab.spack.io/api/v4/projects/zack%2Fmy_test_proj/pipelines?updated_after="
    assert template[117:] == "&ref={0}"


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
        assert status["state"] == test_case["state"]
        assert status["description"] == test_case["description"]


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

    gh_commit = Mock()
    gh_commit.create_status.return_value = AttrDict({"state": "error"})
    gh_repo = Mock()
    gh_repo.get_commit.return_value = gh_commit

    bridge = SpackCIBridge.SpackCIBridge(gitlab_host="https://gitlab.spack.io",
                                         gitlab_project="zack/my_test_proj",
                                         github_project="zack/my_test_proj")
    bridge.py_gh_repo = gh_repo
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
        bridge.post_pipeline_status(open_prs)
        assert mock_urlopen.call_count == 2
        assert gh_repo.get_commit.call_count == 1
        assert gh_commit.create_status.call_count == 1
    out, err = capfd.readouterr()
    expected_content = "Posting status for pr1_readme / aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    assert expected_content in out
    del os.environ["GITHUB_TOKEN"]
