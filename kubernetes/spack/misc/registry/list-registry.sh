#! /usr/bin/env sh

pretty() {
    if [ '!' -t 1 ] ; then
        tr -d '\r'
        return
    fi

    tr -d '\r' | sed 's/^\([^ ]\+\):$/'$'\x1b[0;32m''\1'$'\x1b[0m'':/g'
}

subscript='echo "$( basename $( dirname $( dirname {} ) ) ):"'
subscript="${subscript}"' ; find {} -mindepth 1 -maxdepth 1'
subscript="${subscript}"'       -exec basename "{""}" ";" | sed "s/^/    /g"'
subscript="${subscript}"' ; echo'

exec kubectl exec -t -n spack deployments/registry -- \
    find /var/lib/registry/docker/registry/v2/repositories \
        -mindepth 3 \
        -maxdepth 3 \
        -iname 'tags' \
        -exec sh -c "$subscript" ';' | pretty

