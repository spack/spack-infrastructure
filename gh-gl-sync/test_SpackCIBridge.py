import SpackCIBridge


# Test the list_github_prs method.
def test_list_github_prs(capfd):
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


# Test the get_synced_prs method.
def test_get_synced_prs(capfd):
    bridge = SpackCIBridge.SpackCIBridge()
    bridge.fetch_gitlab_prs = lambda *args: None
    bridge.gitlab_pr_output = b"""
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa	refs/heads/github/pr1_example
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb	refs/heads/github/pr2_another_try
    """
    assert bridge.get_synced_prs() == ["pr1_example", "pr2_another_try"]
    out, err = capfd.readouterr()
    assert out == "Synced PRs:\n    pr1_example\n    pr2_another_try\n"


# Test the get_prs_to_delete method.
def test_get_prs_to_delete(capfd):
    open_prs = ["pr3_try_this", "pr4_new_stuff"]
    synced_prs = ["pr1_first_try", "pr2_different_approach", "pr3_try_this"]
    bridge = SpackCIBridge.SpackCIBridge()
    closed_refspecs = bridge.get_prs_to_delete(open_prs, synced_prs)
    assert closed_refspecs == [":github/pr1_first_try", ":github/pr2_different_approach"]
    out, err = capfd.readouterr()
    assert out == "Synced Closed PRs:\n    pr1_first_try\n    pr2_different_approach\n"


# Test the get_open_refspecs method.
def test_get_open_refspecs():
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


# Test starting & stopping ssh-agent.
def test_ssh_agent():
    import os

    # Local function to check if a PID is running or not.
    def check_pid(pid):
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
