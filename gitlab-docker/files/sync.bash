#! /usr/bin/env bash

set -e

apt-get -qyy update
apt-get -qyy install                                      \
        build-essential ca-certificates curl       g++    \
        gcc             gfortran        git        gnupg2 \
        iproute2        lmod            lua-posix  make   \
        openssh-server  python          python-pip tcl

if [ -z "$DOWNSTREAM_CI_REPO" ] ; then
    echo "Warning: missing variable: DOWNSTREAM_CI_REPO" >&2
fi

git config --global user.email "robot@docker.container"
git config --global user.name "Automated Sync"

( git clone "$UPSTREAM_REPO" /spack || true ) 2> /dev/null

if [ '!' -d /spack-sync ] ; then
    git init /spack-sync
  (
    cd /spack-sync
    git remote add upstream "$UPSTREAM_REPO"
    git remote add downstream "$DOWNSTREAM_CI_REPO"
    git fetch --all --prune
  )
fi

trap "exit" INT TERM QUIT
trap "exit" EXIT

set +e
cd /spack-sync
while sleep 5 ; do
    git fetch --all --prune
    if [ "$?" '!=' '0' ] ; then continue ; fi

    upstream_sha="$( git rev-parse "upstream/$UPSTREAM_REF" )"
    if [ "$?" '!=' '0' ] ; then continue ; fi

    downstream_sha="$(
        git log -n 1 --format='%s' "downstream/$UPSTREAM_REF" 2> /dev/null )"

    if [ "$upstream_sha" '=' "$downstream_sha" ] ; then
        continue
    fi

    # Force HEAD to point to upstream ref
    git branch -D sync 2> /dev/null || true
    git checkout -b sync
    git reset --hard "upstream/$UPSTREAM_REF"

    # Checkout same version under /spack
    (
        cd /spack
        git checkout "$upstream_sha"
    )
    source /spack/share/spack/setup-env.sh

    # Modify HEAD here
    (
        cdash_host="http://cdash:${CDASH_INTERNAL_WEB_PORT}"
        cdash_submit_url="${cdash_host}/cdash/submit.php?project=spack"

        (
            cat /files/release.yaml
            echo "  cdash: [\"${cdash_submit_url}\"]"
        ) > etc/spack/defaults/release.yaml

        cp /spack/share/spack/docker/os-container-mapping.yaml /OSCM-orig

        cp /files/os-container-mapping.yaml \
            share/spack/docker/os-container-mapping.yaml

        cp /files/os-container-mapping.yaml \
            /spack/share/spack/docker/os-container-mapping.yaml

        spack release-jobs                               \
            --spec-set "etc/spack/defaults/release.yaml" \
            --mirror-url http://todo.mirror.com          \
            --cdash-url  "${cdash_host}"                 \
            --shared-runner-tag shell                    \
            --output-file ".gitlab-ci.yml"               \
            --resolve-deps-locally                       \
            --print-summary

        cp /OSCM-orig /spack/share/spack/docker/os-container-mapping.yaml

        git add                                          \
            .gitlab-ci.yml                               \
            etc/spack/defaults/release.yaml              \
            share/spack/docker/os-container-mapping.yaml

        git commit -m 'ci commit'
    )

    # Squash + Push
    git reset "$( git commit-tree HEAD^{tree} -m "$upstream_sha" )"
    git push --force "$DOWNSTREAM_CI_REPO" "sync:$UPSTREAM_REF"

    # Clean up
    git checkout "upstream/$UPSTREAM_REF"
    git branch -D sync
done
