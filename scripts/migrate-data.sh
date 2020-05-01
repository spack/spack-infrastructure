#! /usr/bin/env bash
#
# Copy data from one EBS volume to another.  Useful for when you need to migrate
# data to a larger volume.
#
# This script requires that both the source and destination volumes not be
# assigned to any persistent volumes.  If they are:
#
#     1. Confirm/change the reclaim policy of the PV to "Retain".
#     2. If the PV is bound to any PVCs, delete them or unbind the PV from them.
#     3. Delete the PV.
#
# Usage: Run with no arguments, all input is prompted for interactively.

set -eo pipefail

lookup_pv_by_ebs_id() {
    local id="$1"
    local found_var="$2"
    local name_var="$3"
    local id_var="$4"
    local capacity_var="$5"

    local columns='NAME:.metadata.name'
    columns="$columns,ID:.spec.awsElasticBlockStore.volumeID"
    columns="$columns,CAP:.spec.capacity.storage"

    set +e
    local entry=($( kubectl get pv -o custom-columns="$columns" \
                | tail -n +2 \
                | egrep "^[^ ]+ +[^ ]+/$id +" \
                | head -n 1 ))
    set -e

    local found=1
    if [ "${#entry[@]}" '!=' 0 ] ; then
        found=0
    fi

    if [ -n "$found_var" ] ; then
        eval "$found_var=\"$found\""
    fi

    if [ -n "$name_var" ] ; then
        eval "$name_var=\"${entry[0]}\""
    fi

    if [ -n "$id_var" ] ; then
        eval "$id_var=\"${entry[1]}\""
    fi

    if [ -n "$capacity_var" ] ; then
        eval "$capacity_var=\"${entry[2]}\""
    fi

    if [ -z "$found_var" ] ; then
        return $found_var
    fi
}

lookup_bound_pvc_by_pv() {
    local pv_name="$1"
    local found_var="$2"
    local namespace_var="$3"
    local name_var="$4"

    set +e
    local entry=($( kubectl get pvc --all-namespaces \
                | tail -n +2 \
                | egrep "Bound +$pv_name " \
                | head -n 1 ))
    set -e

    local found=1
    if [ "${#entry[@]}" '!=' 0 ] ; then
        found=0
    fi

    if [ -n "$found_var" ] ; then
        eval "$found_var=\"$found\""
    fi

    if [ -n "$namespace_var" ] ; then
        eval "$namespace_var=\"${entry[0]}\""
    fi

    if [ -n "$name_var" ] ; then
        eval "$name_var=\"${entry[1]}\""
    fi

    if [ -z "$found_var" ] ; then
        return $found_var
    fi
}

check_ebs_id() {
    local id="$1"
    local result_var="$2"

    lookup_pv_by_ebs_id "$id" pv_found pv_name pv_id

    local result=0

    if [ "$pv_found" '=' '0' ] ; then
        lookup_bound_pvc_by_pv "$pv_name" pvc_found pvc_namespace pvc_name

        result=1

        echo "Cannot use volume with ID \"$pv_id\"." >&2
        echo "Volume is already mapped to a PV ($pv_name)." >&2
        if [ "$pv_found" '=' '0' ] ; then
            result=2
            echo "The PV is also bound to a PVC ($pvc_namespace/$pvc_name)." >&2
        fi
        echo
    fi

    if [ -z "$result_var" ] ; then
        return $result
    fi

    eval "$result_var=\"$result\""
}

while True ; do
    echo 'Enter source volume ID (Example: "vol-1234...")'
    echo -n ' > '
    read source_volume_id

    if check_ebs_id "$source_volume_id" ; then break ; fi
done

while True ; do
    echo 'Enter destination volume ID (Example: "vol-1234...")'
    echo -n ' > '
    read destination_volume_id

    if [ "$destination_volume_id" '=' "$source_volume_id" ] ; then
        echo -n "Destination volume ID must be different" >&2
        echo    " from the source volume ID." >&2
        continue
    fi

    if check_ebs_id "$destination_volume_id" ; then break ; fi
done

echo 'Source capacity (Example: "100Gi")'
echo -n ' > '
read source_capacity

echo 'Destination capacity (Example: "100Gi")'
echo -n ' > '
read destination_capacity

while True ; do
    echo
    echo "Source volume: $source_volume_id ($source_capacity)"
    echo "Destination volume: $destination_volume_id ($destination_capacity)"
    echo
    echo -n "Continue (y/[n]) ? "
    read ok_continue

    if [ "$ok_continue" '=' 'y' ] ; then
        ok_continue=0
        break
    fi

    if [ "$ok_continue" '=' 'n' ] ; then
        ok_continue=1
        break
    fi

    continue
done

if [ "$ok_continue" '!=' '0' ] ; then
    exit
fi

echo
echo '[Creating maintenance namespace]'
kubectl apply -f - << EOF
---
apiVersion: v1
kind: Namespace
metadata:
  name: maintenance
EOF

echo
echo '[Creating PVs]'
kubectl apply -f - << EOF
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: data-copy-source
spec:
  storageClassName: "us-east-1a"
  accessModes:
  - ReadWriteOnce
  capacity:
    storage: ${source_capacity}
  persistentVolumeReclaimPolicy: Retain
  awsElasticBlockStore:
    fsType: ext4
    volumeID: aws://us-east-1a/${source_volume_id}

---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: data-copy-destination
spec:
  storageClassName: "us-east-1a"
  accessModes:
  - ReadWriteOnce
  capacity:
    storage: ${destination_capacity}
  persistentVolumeReclaimPolicy: Retain
  awsElasticBlockStore:
    fsType: ext4
    volumeID: aws://us-east-1a/${destination_volume_id}
EOF

echo
echo '[Creating PVCs]'
kubectl apply -f - << EOF
---
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: data-copy-source
  namespace: maintenance
spec:
  accessModes:
    - ReadWriteOnce
  volumeMode: Filesystem
  volumeName: data-copy-source
  resources:
    requests:
      storage: ${source_capacity}
  storageClassName: us-east-1a

---
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: data-copy-destination
  namespace: maintenance
spec:
  accessModes:
    - ReadWriteOnce
  volumeMode: Filesystem
  volumeName: data-copy-destination
  resources:
    requests:
      storage: ${destination_capacity}
  storageClassName: us-east-1a
EOF

echo
echo '[Waiting for PVCs to bind]'
until lookup_bound_pvc_by_pv "data-copy-source" ; do sleep 1 ; done
until lookup_bound_pvc_by_pv "data-copy-destination" ; do sleep 1 ; done

echo
echo '[Creating Migration Pod]'
kubectl apply -f - << EOF
---
apiVersion: v1
kind: Pod
metadata:
  name: migrate
  namespace: maintenance
spec:
  containers:
  - name: transfer
    image: "alpine:latest"
    command: ["sh", "-c",
        "apk add rsync ; touch /ready ; until [ -f /done ] ; do sleep 5 ; done"]
    imagePullPolicy: Always
    volumeMounts:
      - { "name": "source", "mountPath": "/source" }
      - { "name": "destination", "mountPath": "/destination" }
  volumes:
    - name: source
      persistentVolumeClaim:
        claimName: data-copy-source
    - name: destination
      persistentVolumeClaim:
        claimName: data-copy-destination
  nodeSelector:
    "beta.kubernetes.io/instance-type": "t2.medium"
EOF

echo
echo '[Waiting for POD to be ready]'
until kubectl exec -n maintenance migrate -- true &> /dev/null
do
    sleep 5
done

echo 'Source Mount:'
kubectl exec -n maintenance migrate -- df -h /source
kubectl exec -n maintenance migrate -- ls -1 /source | head -n 5
echo '...'
echo

echo 'Destination Mount:'
kubectl exec -n maintenance migrate -- df -h /destination
kubectl exec -n maintenance migrate -- ls -1 /source | head -n 5
echo '...'
echo

while True ; do
    echo
    echo -n "Continue (y/[n]) ? "
    read ok_continue

    if [ "$ok_continue" '=' 'y' ] ; then
        ok_continue=0
        break
    fi

    if [ "$ok_continue" '=' 'n' ] ; then
        ok_continue=1
        break
    fi

    continue
done

if [ "$ok_continue" '=' '0' ] ; then
    while True ; do
        echo
        echo -n "Clear destination before copying (y/[n]) ? "
        read ok_clear

        if [ "$ok_clear" '=' 'y' ] ; then
            ok_clear=0
            break
        fi

        if [ "$ok_clear" '=' 'n' ] ; then
            ok_clear=1
            break
        fi

        continue
    done

    if [ "$ok_clear" '=' '0' ] ; then
        echo
        echo '[Clearing Destination]'
        kubectl exec -n maintenance migrate -- sh -c \
            'until [ -f /ready ] ; do sleep 5 ; done'
        kubectl exec -n maintenance migrate -- \
            find /destination -mindepth 1 -delete
    fi

    echo
    echo '[Performing Copy]'
    kubectl exec -n maintenance migrate -- sh -c \
        'until [ -f /ready ] ; do sleep 5 ; done'
    time kubectl exec -n maintenance migrate -- rsync -avz /source/ /destination
    echo
fi

echo
echo '[Cleaning up]'

set +e
kubectl delete pods -n maintenance migrate
kubectl delete pvc -n maintenance data-copy-source data-copy-destination
kubectl delete pv data-copy-source data-copy-destination
kubectl delete namespace maintenance
set -e

