#! /usr/bin/env python

# If you have an existing PVC that you'd like to change:
#  - the capacity
#  - the storage class
#  - the storage mode
#  - ... or anything else, really
#
# The obvious thing to try is to create a new manifest with your changes and
# apply it:
#
#  $ $EDITOR pvc-with-changes.yaml
#  $ kubectl apply -f pvc-with-changes.yaml
#
# ...except this doesn't work, because kubernetes sets immutability constraints
# on these properties.  The proper way to handle this situation is to create a
# new PVC with your desired changes, copy the data from the old PVC to the new
# PVC, and fiddle with a lot of tedious and error-prone kubernetes accounting
# in order to make the migration transparent to existing workloads.  That's
# what this script does.  Simply pass the manifest that you would have naively
# applied directly to the cluster and it takes care of the rest.
#
#  $ ./migrate-pvc.py pvc-with-changes.yaml

import copy
import json
import os
import subprocess
import re
import sys
import time
import yaml

RE_VALID_PVC_NAME = re.compile(
    r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$')


def kubectl(args, stdin=None,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
    sys.stdout.flush()
    sys.stderr.flush()
    p = subprocess.Popen(
            ['kubectl'] + list(args),
            text=True,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr)

    if (stdin == subprocess.PIPE or
        stdout == subprocess.PIPE or
        stderr == subprocess.PIPE):
        return p

    return p.wait()


def kube_op(op):
    def result(*manifests):
        p = kubectl(
                [op, '-f', '-'],
                stdin=subprocess.PIPE,
                stdout=None,
                stderr=subprocess.STDOUT)

        yaml.dump_all(list(manifests), stream=p.stdin)
        p.stdin.flush()
        p.stdin.close()
        code = p.wait()
        if code != 0:
            sys.exit(code)

    result.name = f'k{op}'
    return result


kapply = kube_op('apply')


def main(inputf):
    IS_TTY = os.isatty(sys.stdout.fileno())

    d = list(yaml.load_all(inputf, Loader=yaml.SafeLoader))

    if len(d) == 0:
        sys.stderr.write('Error: empty manifest')
        return 1

    if len(d) > 1:
        sys.stderr.write('Warning: received manifest with more than '
                         'one item... processing the first item only\n')

    d = d[0]

    if d['kind'] != 'PersistentVolumeClaim':
        sys.stderr.write('Error: received non-pvc manifest.')
        return 1

    orig_pvc_name = d['metadata']['name']
    passed_pvc = copy.deepcopy(d)

    namespace = d['metadata'].get('namespace', 'default')

    # query for the original PVC in case we need to repurpose its PV at the end
    proc = kubectl(
            ['get', 'persistentvolumeclaim', '--namespace', namespace,
              orig_pvc_name, '-o', 'json'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while querying a PVC:'
                         f'\n\n{errs}')
        return 1

    orig_pvc = json.loads(outs)

    # filter out the internals
    meta = orig_pvc.get('metadata', {})
    meta.get('annotations', {}).pop(
            'kubectl.kubernetes.io/last-applied-configuration', None)

    meta.get('annotations', {}).pop(
            'pv.kubernetes.io/bind-completed', None)

    meta.get('annotations', {}).pop(
            'pv.kubernetes.io/bound-by-controller', None)

    meta.get('annotations', {}).pop(
            'volume.beta.kubernetes.io/storage-provisioner', None)

    meta.get('annotations', {}).pop(
            'volume.kubernetes.io/storage-provisioner', None)

    meta.pop('creationTimestamp', None)
    meta.pop('finalizers', None)
    meta.pop('resourceVersion', None)
    meta.pop('selfLink', None)
    meta.pop('uid', None)

    spec = orig_pvc.get('spec', {})
    spec.pop('volumeName', None)

    orig_pvc.pop('status', None)

    tmp_pvc_name = f'{orig_pvc_name}-migration-target'

    counter = -1
    while kubectl(['get', 'pvc', '--namespace', namespace, tmp_pvc_name]) == 0:
        counter += 1
        tmp_pvc_name = f'{orig_pvc_name}-migration-target-{counter}'

    print('Creating temporary PVC...')
    d['metadata']['name'] = tmp_pvc_name
    kapply(d)
    print()

    pod_name = f'{tmp_pvc_name}-pod'
    counter = -1
    while kubectl(['get', 'pod', '--namespace', namespace, pod_name]) == 0:
        counter += 1
        pod_name = f'{tmp_pvc_name}-pod-{counter}'

    print('Creating migration pod...')
    kapply({
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': pod_name,
            'namespace': namespace
        },
        'spec': {
            'restartPolicy': 'Never',
            'containers': [{
                'name': 'migrate',
                'image': 'debian:11-slim',
                'command': ['/bin/bash', '-c'],
                'args': ['( apt-get update && '
                         'apt-get install -qy rsync ) &>/dev/null && '
                          'rsync -avPS --delete /mnt/src/ /mnt/dst/'],
                'volumeMounts': [
                    {'name': 'src', 'mountPath': '/mnt/src', 'readOnly': True},
                    {'name': 'dst', 'mountPath': '/mnt/dst'}
                ],
                'resources': {
                    'requests': {
                        'cpu': '200m',
                        'ephemeral-storage': '500Mi',
                        'memory': '256Mi'
                    }
                }
            }],
            'volumes': [
                {
                    'name': 'src',
                    'persistentVolumeClaim': {'claimName': orig_pvc_name}
                },
                {
                    'name': 'dst',
                    'persistentVolumeClaim': {'claimName': tmp_pvc_name}
                }
            ]
        }
    })
    print()

    print('Waiting for data copy to complete...')

    if IS_TTY:
        print('\nRun the following command in another shell for progress:\n'
              f'kubectl logs -f --namespace {namespace} {pod_name}\n')

    template='''
        {{- range .status.conditions -}}
          {{- if and (eq .reason "PodCompleted") (eq .status "True") -}}
          OK
          {{- end -}}
        {{- end -}}
    '''
    while True:
        proc = kubectl(
                ['get', 'pods', '--namespace', namespace,
                  pod_name, '-o', f'template={template}'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while waiting for '
                             f'the data copy to complete:\n\n{errs}')
            return 1

        if outs == 'OK':
            break

        time.sleep(5)


    print('Cleaning up migration pod...')
    kubectl(['delete', 'pods', '--namespace', namespace, pod_name],
            stdout=None,
            stderr=subprocess.STDOUT)
    print()

    print('Preparing volumes for swap...')

    # query oldPVC's PV
    proc = kubectl(
            ['get', 'persistentvolumeclaim', '--namespace', namespace,
              orig_pvc_name, '-o', 'jsonpath={.spec.volumeName}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while querying a PVC:'
                         f'\n\n{errs}')
        return 1

    old_pv = outs

    # query newPVC's PV
    proc = kubectl(
            ['get', 'persistentvolumeclaim', '--namespace', namespace,
              tmp_pvc_name, '-o', 'jsonpath={.spec.volumeName}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while querying a PVC:'
                         f'\n\n{errs}')
        return 1

    new_pv = outs

    # query old PV's claimRef
    proc = kubectl(['get', 'persistentvolume', old_pv,
                    '-o', 'jsonpath={.spec.claimRef}'],
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE)

    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while '
                         'fetching PV claimRef:'
                         f'\n\n{errs}')
        return 1

    old_claim_ref = yaml.load(outs, Loader=yaml.SafeLoader)


    # query new PV's claimRef
    proc = kubectl(['get', 'persistentvolume', new_pv,
                    '-o', 'jsonpath={.spec.claimRef}'],
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE)

    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while '
                         'fetching PV claimRef:'
                         f'\n\n{errs}')
        return 1

    new_claim_ref = yaml.load(outs, Loader=yaml.SafeLoader)

    # query original PV reclaim policy
    proc = kubectl(
            ['get', 'persistentvolume', old_pv,
              '-o', 'jsonpath={.spec.persistentVolumeReclaimPolicy}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while querying a PV:'
                         f'\n\n{errs}')
        return 1

    old_pv_reclaim_policy = outs.strip()

    if old_pv_reclaim_policy != 'Retain':
        # retain old PV
        kubectl(['patch', 'persistentvolume', old_pv, '--patch',
                 '{"spec": {"persistentVolumeReclaimPolicy": "Retain"}}'],
                 stdout=None, stderr=subprocess.STDOUT)

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while '
                             'patching a PV!')
            return 1

    # query new PV reclaim policy
    proc = kubectl(
            ['get', 'persistentvolume', new_pv,
              '-o', 'jsonpath={.spec.persistentVolumeReclaimPolicy}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while querying a PV:'
                         f'\n\n{errs}')
        return 1

    new_pv_reclaim_policy = outs.strip()

    if new_pv_reclaim_policy != 'Retain':
        # retain new PV
        kubectl(['patch', 'persistentvolume', new_pv, '--patch',
                 '{"spec": {"persistentVolumeReclaimPolicy": "Retain"}}'],
                 stdout=None, stderr=subprocess.STDOUT)

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while '
                             'patching a PV!')
            return 1

    print()

    print('Deleting PVCs...')
    kubectl(['delete', 'persistentvolumeclaim', '--namespace', namespace,
             orig_pvc_name, tmp_pvc_name],
             stdout=None, stderr=subprocess.STDOUT)

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while deleting PVCs!')
        return 1

    print()

    print('Recreating original PVC using new PV...')
    tmp = copy.deepcopy(passed_pvc)
    tmp['spec']['volumeName'] = new_pv
    kapply(tmp)
    del tmp
    print()

    # query new PVC metadata
    proc = kubectl(
            ['get', 'persistentvolumeclaim', '--namespace', namespace,
                orig_pvc_name, '-o', 'jsonpath={.metadata}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()

    if proc.returncode != 0:
        sys.stderr.write('Error: something went wrong while querying a PVC:'
                         f'\n\n{errs}')
        return 1

    new_pvc_metadata = yaml.load(outs.strip(), Loader=yaml.SafeLoader)

    print('Migrating claim reference to new PV...')
    kubectl(['patch', 'persistentvolume', old_pv, '--patch',
            '{"spec": {"claimRef": null}}'],
             stdout=None, stderr=subprocess.STDOUT)

    claim_ref = copy.deepcopy(old_claim_ref)
    claim_ref['resourceVersion'] = new_pvc_metadata['resourceVersion']
    claim_ref['uid'] = new_pvc_metadata['uid']
    claim_ref = json.dumps(claim_ref)

    kubectl(['patch', 'persistentvolume', new_pv, '--patch',
            f'{{"spec": {{"claimRef": {claim_ref}}}}}'],
             stdout=None, stderr=subprocess.STDOUT)

    print()


    print('Waiting for new PV to bind...')
    template='''
        {{- if eq .status.phase "Bound" -}}
          OK
        {{- end -}}
    '''
    while True:
        proc = kubectl(
                ['get', 'persistentvolume', new_pv,
                  '-o', f'template={template}'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while waiting for '
                             f'a PV to bind:\n\n{errs}')
            return 1

        if outs == 'OK':
            break

        time.sleep(5)

    if old_pv_reclaim_policy != 'Retain':
        # restore original PV retention policy
        kubectl(['patch', 'persistentvolume', new_pv, '--patch',
                 f'{{"spec": {{"persistentVolumeReclaimPolicy": '
                 f'"{old_pv_reclaim_policy}"}}}}'],
                 stdout=None, stderr=subprocess.STDOUT)

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while '
                             'patching a PV!')
            return 1

    print()

    print('\nData migration complete!\n\n'
          f'The original PV ({old_pv}) (and its data!)\n'
          'has been left intact. It would need to be bound\n'
          'to a new PVC to be useful\n')

    answer = '0'
    if IS_TTY:
        print('What would you like to do with it?\n')

        while True:
            print('    0              - do nothing, leave it as-is\n\n'
                  '    1              - delete it\n\n'
                  '    <new-pvc-name> - create a new pvc with the\n'
                  '                     given name and bind the\n'
                  '                     original PV to it\n')

            answer = input('\nenter response: ').strip()

            if answer == '0' or answer == '1':
                break

            if not answer:
                continue

            if not RE_VALID_PVC_NAME.match(answer):
                print(f'"{answer}" is not a valid PVC name!\n')
                continue

            if kubectl(['get', 'pvc', '--namespace', namespace, answer]) != 0:
                break

            print(f'There is already a PVC named "{answer}" '
                  f'in the "{namespace}" namespace!\n')
    else:
        print('...or you can run the following command to delete it:\n')
        print(f'    kubectl delete persistentvolume {old_pv}\n')

    if answer == '1':  # delete
        print('Deleting original PV...')
        kubectl(['delete', 'persistentvolume', old_pv],
                 stdout=None, stderr=subprocess.STDOUT)

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while deleting PVs!')
            return 1

        print()

    elif answer != '0':  # repurpose
        print('Recreating original PVC using original PV...')
        orig_pvc['metadata']['name'] = answer
        orig_pvc['spec']['volumeName'] = old_pv
        kapply(orig_pvc)
        print()

        # query new PVC metadata
        proc = kubectl(
                ['get', 'persistentvolumeclaim', '--namespace', namespace,
                    answer, '-o', 'jsonpath={.metadata}'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()

        if proc.returncode != 0:
            sys.stderr.write('Error: something went wrong while querying a '
                             f'PVC:\n\n{errs}')
            return 1

        new_pvc_metadata = yaml.load(outs.strip(),
                                     Loader=yaml.SafeLoader)

        claim_ref = copy.deepcopy(new_claim_ref)
        claim_ref['resourceVersion'] = new_pvc_metadata['resourceVersion']
        claim_ref['uid'] = new_pvc_metadata['uid']
        claim_ref = json.dumps(claim_ref)

        kubectl(['patch', 'persistentvolume', old_pv, '--patch',
                f'{{"spec": {{"claimRef": {claim_ref}}}}}'],
                 stdout=None, stderr=subprocess.STDOUT)

        print()

        print('Waiting for new PVC to bind...')
        template='''
            {{- if eq .status.phase "Bound" -}}
              OK
            {{- end -}}
        '''
        while True:
            proc = kubectl(
                    ['get', 'persistentvolume', old_pv,
                      '-o', f'template={template}'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            outs, errs = proc.communicate()

            if proc.returncode != 0:
                sys.stderr.write('Error: something went wrong while'
                                 f'waiting for a PV to bind:\n\n{errs}')
                return 1

            if outs == 'OK':
                break

            time.sleep(5)

        if old_pv_reclaim_policy != 'Retain':
            # restore original PV retention policy
            kubectl(['patch', 'persistentvolume', old_pv, '--patch',
                     f'{{"spec": {{"persistentVolumeReclaimPolicy": '
                     f'"{old_pv_reclaim_policy}"}}}}'],
                     stdout=None, stderr=subprocess.STDOUT)

            if proc.returncode != 0:
                sys.stderr.write('Error: something went wrong while '
                                 'patching a PV!')
                return 1

        print()

    print('Done!\n')
    return 0


if __name__ == '__main__':
    f = sys.stdin
    if sys.argv[1:]:
        f = open(sys.argv[1])

    with f:
        result = main(f)
        if result is None:
            result = 0

    sys.exit(result)
