export GITLAB_SSH_KEY_BASE64="$( base64 < /secrets/gitlab-ssh-key )"
export GITHUB_TOKEN="$( cat /secrets/github-access-token )"
# TODO: update these repos after testing
python3 /scripts/SpackCIBridge.py \
  'scottwittenburg/gitlab-ci-tests' \
  'ssh.gitlab.spack.io' \
  'scott/gitlab-ci-tests' \
