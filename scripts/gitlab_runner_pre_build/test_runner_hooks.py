"""Run each runner's pre/post build hooks in one bash process, as GitLab Runner does."""

import pathlib
import shutil
import subprocess
import sys

import pytest

tomllib = pytest.importorskip("tomllib")
yaml = pytest.importorskip("yaml")

RUNNERS_DIR = pathlib.Path(__file__).resolve().parents[2] / "k8s" / "production" / "runners"
# public/ and protected/ runners; signing/release.yaml is one level up and not matched
RUNNER_CONFIGS = sorted(RUNNERS_DIR.glob("*/*/*/release.yaml"))
LINUX_CONFIGS = [p for p in RUNNER_CONFIGS if not p.parent.name.endswith("-win")]
WINDOWS_CONFIGS = [p for p in RUNNER_CONFIGS if p.parent.name.endswith("-win")]

PRE_BUILD_URL = (
    "https://raw.githubusercontent.com/spack/spack-infrastructure/main/"
    "scripts/gitlab_runner_pre_build/pre_build.py"
)

# stands in for pre_build.py: derives fake credentials from the token
FAKE_PRE_BUILD = """
import os, sys
token = os.environ.get("GITLAB_OIDC_TOKEN")
if not token:
    sys.exit(0)
print(f'export AWS_ACCESS_KEY_ID="key-from-{token}"')
print(f'export SEEN_DURATION="{os.environ.get("SPACK_CI_CREDENTIALS_DURATION", "unset")}"')
"""

# stands in for the job's script: records what a build process can see
JOB_SCRIPT = """
set -x
mkdir -p subdir && cd subdir
env > ../build-env.txt
"""

TOKEN = "TOKEN123"


def _hooks(config):
    docs = [d for d in yaml.safe_load_all(config.read_text()) if d]
    release = next(d for d in docs if d["kind"] == "HelmRelease")
    runner = tomllib.loads(release["spec"]["values"]["runners"]["config"])["runners"][0]
    return runner["pre_build_script"], runner["post_build_script"]


def _run_job(config, tmp_path, env):
    fake = tmp_path / "fake_pre_build.py"
    fake.write_text(FAKE_PRE_BUILD)
    pre, post = (h.replace(PRE_BUILD_URL, fake.as_uri()) for h in _hooks(config))
    work = tmp_path / "work"
    work.mkdir()
    script = "\n".join(["set -eo pipefail", pre, JOB_SCRIPT, post])
    base = {"PATH": f"{pathlib.Path(sys.executable).parent}:/usr/bin:/bin", "HOME": str(work)}
    result = subprocess.run(
        ["bash", "-c", script], cwd=work, env={**base, **env}, capture_output=True, text=True
    )
    return work, result


def test_hooks_identical_across_runners():
    for configs in (LINUX_CONFIGS, WINDOWS_CONFIGS):
        assert len({_hooks(c)[1] for c in configs}) == 1, "post_build_script copies differ"
    # Linux pre_build_script copies are run below; Windows ones can only be compared
    assert len({_hooks(c)[0] for c in WINDOWS_CONFIGS}) == 1, "Windows pre_build_script copies differ"


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
@pytest.mark.parametrize("config", LINUX_CONFIGS, ids=lambda p: str(p.relative_to(RUNNERS_DIR).parent))
def test_deferred_credentials(config, tmp_path):
    work, result = _run_job(
        config,
        tmp_path,
        {"GITLAB_OIDC_TOKEN": TOKEN, "SPACK_CI_POST_BUILD_PUSH": "env > push-env.txt"},
    )
    assert result.returncode == 0, result.stderr

    build_env = (work / "build-env.txt").read_text()
    assert TOKEN not in build_env
    assert "AWS_ACCESS_KEY_ID" not in build_env

    push_env = (work / "subdir" / "push-env.txt").read_text()
    assert f"AWS_ACCESS_KEY_ID=key-from-{TOKEN}" in push_env
    assert "SEEN_DURATION=3600" in push_env
    assert TOKEN not in push_env.replace(f"key-from-{TOKEN}", "")

    # the job's `set -x` must not trace the token in post_build_script
    assert TOKEN not in result.stderr.replace(f"key-from-{TOKEN}", "")


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
@pytest.mark.parametrize("config", LINUX_CONFIGS, ids=lambda p: str(p.relative_to(RUNNERS_DIR).parent))
def test_deferred_without_token_fails(config, tmp_path):
    work, result = _run_job(config, tmp_path, {"SPACK_CI_POST_BUILD_PUSH": "touch pushed"})

    assert result.returncode != 0
    assert "saved no GITLAB_OIDC_TOKEN" in result.stdout
    assert not (work / "subdir" / "pushed").exists()


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
@pytest.mark.parametrize("config", LINUX_CONFIGS, ids=lambda p: str(p.relative_to(RUNNERS_DIR).parent))
def test_not_opted_in(config, tmp_path):
    work, result = _run_job(config, tmp_path, {"GITLAB_OIDC_TOKEN": TOKEN})
    assert result.returncode == 0, result.stderr

    build_env = (work / "build-env.txt").read_text()
    assert f"AWS_ACCESS_KEY_ID=key-from-{TOKEN}" in build_env
    assert "SEEN_DURATION=unset" in build_env
    assert "GITLAB_OIDC_TOKEN" not in build_env
