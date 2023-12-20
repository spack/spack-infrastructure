import pytest
from click.testing import CliRunner
from spack_secrets import update
from spack_secrets.update import update as main


@pytest.fixture(autouse=True)
def _patch_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("KUBECONFIG", ".kube/config")
    monkeypatch.setattr("kubernetes.config.load_config", lambda: None)

    # Patch print_cluster_info so it doesn't try to reach out to the k8s API
    monkeypatch.setattr(update, "print_cluster_info", lambda: None)

    # Create dummy kubeseal exec
    (tmp_path / "kubeseal").touch(mode=777)
    monkeypatch.syspath_prepend(tmp_path)


def test_no_secrets_file_supplied():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0
    assert "SECRETS_FILE must be supplied" in result.output


def test_kubeconfig_not_set(monkeypatch):
    monkeypatch.delenv("KUBECONFIG", raising=False)

    runner = CliRunner()
    result = runner.invoke(main, "foo/bar.yaml")
    assert result.exit_code != 0
    assert "KUBECONFIG" in result.output


def test_kubeseal_not_found(monkeypatch):
    # Delete path so kubeseal can't be found
    monkeypatch.delenv("PATH")

    runner = CliRunner()
    result = runner.invoke(main, "foo/bar.yaml")
    assert result.exit_code != 0
    assert "kubeseal" in result.output


def test_secrets_file_not_found():
    runner = CliRunner()
    result = runner.invoke(main, "foo/bar.yaml")
    assert result.exit_code != 0
    assert "File foo/bar.yaml not found" in result.output


def test_secrets_file_is_folder(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, str(tmp_path))
    assert result.exit_code != 0
    assert "must be a file, not a folder" in result.output
