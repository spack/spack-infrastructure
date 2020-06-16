sh /scripts/install-packages.sh
export GITLAB_SSH_KEY_BASE64="$( base64 < /secrets/gitlab-ssh-key )"
export GITHUB_TOKEN="$( cat /secrets/github-access-token )"
# TODO: update these repos after testing
bash /scripts/github-prs-to-gitlab.sh \
  'scottwittenburg/gitlab-ci-tests' \
  'ssh.gitlab.spack.io' \
  'scott/gitlab-ci-tests'
