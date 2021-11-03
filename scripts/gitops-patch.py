#! /usr/bin/env python

import argparse
import sys
import yaml

parser = argparse.ArgumentParser()

parser.add_argument('orig_file', help='file to apply patch to')
parser.add_argument('patch_file', help='patch to apply')

parser.add_argument('-i',
                    '--index',
                    help='which root-level object to patch (default: 0)',
                    type=int,
                    default=0)

parser.add_argument('-p',
                    '--patch-index',
                    help=('which root-level object to use as'
                          ' the patch (default: 0)'),
                    type=int,
                    default=0)

parser.add_argument('-e',
                    '--environment',
                    help=('replcae {ENV} in the patch with'
                          ' the given value (default: staging)'),
                    default='staging')

def apply_patch(obj, patch):
    for p in patch:
        op = p.get('op', None)
        path = p.get('path', None)
        val = p.get('value', None)

        if not op: continue
        if not path: continue

        ptr = obj
        key = None
        if path:
            if path == '/':
                key = ''
            else:
                tokens = path.split('/')[1:]
                tokens, key = tokens[:-1], tokens[-1]
                for t in tokens:
                    if isinstance(ptr, list):
                        t = int(t)
                    ptr = ptr[t]

        if op == 'add':
            if isinstance(ptr, list):
                if key == '-':
                    ptr.append(val)
                else:
                    key = int(key)
                    ptr.insert(key, val)
            else:
                ptr[key].update(val)
        elif op == 'remove':
            if isinstance(ptr, list):
                if key == '-':
                    ptr.pop()
                else:
                    key = int(key)
                    ptr.remove(key)
            else:
                ptr.pop(key)
        elif op == 'replace':
            if isinstance(ptr, list):
                if key == '-':
                    ptr[-1] = val
                else:
                    key = int(key)
                    ptr[key] = val
            else:
                ptr[key] = val
        else:
            continue  # TODO(opadron): finish this if we ever start caring
                      #                about copy, move, or test


def process_patch(patch, env):
    if isinstance(patch, list):
        return [process_patch(p, env) for p in patch]

    if isinstance(patch, dict):
        return {process_patch(k, env): process_patch(v, env)
                for k, v in patch.items()}

    if isinstance(patch, str):
        return patch.format(ENV=env)

    return patch


def warn(*args):
    sys.stdout.write('\n')
    sys.stdout.write('\x1b[1;33m')
    sys.stdout.write(*args)
    sys.stdout.write('\x1b[0m\n')


# MAIN ENTRY POINT
args = parser.parse_args()
f = sys.stdin
f_name = '<stdin>'
if args.patch_file:
    f = open(args.patch_file)
    f_name = args.patch_file

patch = None
with f:
    try:
        roots = list(yaml.full_load_all(f))
        patch = roots[args.patch_index]
    except yaml.scanner.ScannerError as e:
        warn('patch file failed to parse')
        sys.stdout.write('\x1b[1;31m')
        e.problem_mark.name = f_name
        print(e)
        sys.stdout.write('\x1b[0m')

# some sanity checks
if patch['apiVersion'] != 'v1':
    raise ValueError('patch["apiVersion"] != "v1"')

if patch['kind'] != 'ConfigMap':
    raise ValueError('patch["kind"] != "ConfigMap"')

annotation_missing = (
    (
        (
            (patch.get('metadata') or {})
            .get('annotations') or {}
        )
        .get('cd.spack.io/staged-resource', '0')
    ) in
    (None, 'false', '0', 'off', 'no', 'disabled'))

if annotation_missing:
    raise ValueError('patch annotation missing or disabled:'
                     ' cd.spack.io/staged-resource')

patch = patch.get('data', {}).get('patch', None)
if patch is None:
    raise ValueError('patch.data.patch missing or empty')


try:
    patch = yaml.full_load(patch)
except (yaml.parser.ParserError, yaml.scanner.ScannerError) as e:
    warn('patch data failed to parse')
    sys.stdout.write('\x1b[1;31m')
    print(e)
    sys.stdout.write('\x1b[0m')

orig_file = open(args.orig_file)
orig_file_name = args.orig_file

target = None
with orig_file:
    try:
        roots = list(yaml.full_load_all(orig_file))
        target = roots[args.index]
    except yaml.scanner.ScannerError as e:
        warn('file failed to parse')
        sys.stdout.write('\x1b[1;31m')
        e.problem_mark.name = orig_file_name
        print(e)
        sys.stdout.write('\x1b[0m')

patch = process_patch(patch, env=args.environment)
apply_patch(target, patch)
yaml.dump(target, sys.stdout)
