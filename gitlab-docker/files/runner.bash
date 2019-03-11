#! /usr/bin/bash

apt-get -qyy update
apt-get -qyy install                                      \
        build-essential ca-certificates curl       g++    \
        gcc             gfortran        git        gnupg2 \
        iproute2        lmod            lua-posix  make   \
        openssh-server  python          python-pip tcl

runner="/entrypoint"
config="/etc/gitlab-runner/config.toml"

registered() {
    [ -f "$config" ]
    return $?
}

register() {
    echo "==> $runner register"
    echo
    "$runner" register
}

unregister() {
    echo "==> $runner unregister --name $( hostname )"
    echo
    "$runner" unregister --name "$( hostname )"
    rm -f "$config"
}

force_register() {
    if registered ; then
        unregister
    fi

    register
}

run() {
    echo "==> $runner run ..."
    echo "... --user=gitlab-runner ..."
    echo "... --working-directory=/home/gitlab-runner"
    echo
    "$runner" run --user=gitlab-runner --working-directory=/home/gitlab-runner &

    __runner_pid="$!"
    wait "$__runner_pid"
}

stop() {
    echo "==> $runner stop"
    echo
    "$runner" stop
}

__dirty=1
cleanup() {
    if [ "$__dirty" '=' '0' ] ; then
        return
    fi

    if registered ; then
        unregister
    fi

    sleep 3

    stop

    __dirty=0
}

trap "cleanup" INT TERM QUIT
trap "cleanup" EXIT

force_register
run
