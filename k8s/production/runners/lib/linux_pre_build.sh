echo 'Executing Spack pre-build setup script'

for cmd in "${PY3:-}" python3 python; do
  if command -v > /dev/null "$cmd"; then
    export PY3="$(command -v "$cmd")"
    break
  fi
done

if [ -z "${PY3:-}" ]; then
  echo "Unable to find python3 executable"
  exit 1
fi

$PY3 -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/spack/spack-infrastructure/main/scripts/gitlab_runner_pre_build/pre_build.py', 'pre_build.py')"
$PY3 pre_build.py > envvars

. ./envvars
rm -f envvars
unset GITLAB_OIDC_TOKEN
