import argparse
import copy
import datetime
import os
import os.path
import re
import subprocess
import shutil
import sys
import time
import yaml

import git

parser = argparse.ArgumentParser()
parser.add_argument('--repo', help='repo to monitor', required=True)

parser.add_argument('--staging-branch',
                    help='staging branch',
                    required=True)
parser.add_argument('--source-dir',
                    help=('directory from which to source '
                          'manifests on the production and staging branches'),
                    required=True)

parser.add_argument('--production-branch',
                    help='production branch',
                    required=True)

parser.add_argument('--target-branch', help='target branch', required=True)
parser.add_argument('--target-dir',
                    help=('directory in which to store generated '
                          'manifests on the target branch')
                    , required=True)

parser.add_argument('--interval',
                    help='polling interval',
                    type=int, default=300)
parser.add_argument('--deploy-key',
                    help='path to deployment key',
                    required=True)
parser.add_argument('--user-email', help='email to commit as', required=True)
parser.add_argument('--user-name', help='user name to commit as', required=True)
parser.add_argument('--storage-dir',
                    help='directory to use for persistent storage',
                    required=True)
args = parser.parse_args()


entries_map = {}
special_map = {}
class ParsedEntry:
    def __init__(self, obj, env, update=True):
        global entries_map
        global special_map

        api_version = obj.get('apiVersion', None)
        if not api_version:
            raise ValueError('field missing: "apiVersion"')

        kind = obj.get('kind', None)
        if not kind:
            raise ValueError('field missing: "kind"')

        metadata = obj.get('metadata', None)
        if not metadata:
            raise ValueError('field missing: "metadata"')

        name = metadata.get('name', None)
        if not name:
            raise ValueError('field missing: "metadata.name"')

        namespace = metadata.get('namespace', 'default')

        annotations = metadata.get('annotations', None)
        ignored = (annotations and annotations.get('cd.spack.io/ignore', False))

        tokens = api_version.split('/')
        api_group, api_version = (
                ('builtin', tokens[0]) if len(tokens) == 1 else
                tokens)

        self.api_group = api_group
        self.api_version = api_version
        self.kind = kind
        self.name = name
        self.namespace = namespace
        self.obj = obj
        self.ignored = ignored

        key = (api_group, api_version, kind, namespace, name)
        if update:
            entries_map[env][key] = self

        is_special = (kind == 'ConfigMap' and annotations)
        if is_special:
            dr = annotations.get('cd.spack.io/staged-resource', 'false').lower()
            is_special = (dr not in ('false', '0', 'off', 'no', 'disabled'))

        if is_special and update:
            special_map[env][key] = self


def log(*args):
    sys.stdout.write('\n')
    sys.stdout.write('\x1b[1;34m[')
    sys.stdout.write(str(datetime.datetime.now()))
    sys.stdout.write('] \x1b[1;32m')
    sys.stdout.write(*args)
    sys.stdout.write('\x1b[0m\n')


def warn(*args):
    sys.stdout.write('\n')
    sys.stdout.write('\x1b[1;34m[')
    sys.stdout.write(str(datetime.datetime.now()))
    sys.stdout.write('] \x1b[1;33m')
    sys.stdout.write(*args)
    sys.stdout.write('\x1b[0m\n')


RE_TILDE = re.compile('~0')
RE_SLASH = re.compile('~1')


def process_path_token(tok):
    return RE_TILDE.sub('~', RE_SLASH.sub('/', tok))


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
                tokens = [process_path_token(tok)
                          for tok in path.split('/')[1:]]
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


def read_scalar_from_path(f):
    result = None
    if os.path.exists(f):
        with open(f) as fid:
            result = fid.read().strip()
    return result


def write_scalar_to_path(f, val):
    if not isinstance(val, bytes):
        val = bytes(str(val), 'UTF-8')

    with open(f, 'w') as fid:
        fid.buffer.write(val)


def iter_manifests(path, repo, env):
    for prefix, _, files in os.walk(path):
        for filename in files:
            is_manifest = (filename.endswith('.yaml') or
                           filename.endswith('.yml') or
                           filename.endswith('.json'))

            if not is_manifest:
                continue

            filepath = os.path.join(prefix, filename)
            with open(filepath) as f:
                try:
                    for obj in yaml.full_load_all(f):
                        if not isinstance(obj, dict):
                            continue
                        yield ParsedEntry(obj, env)
                except yaml.scanner.ScannerError as e:
                    warn(f'file failed to parse')
                    sys.stdout.write('\x1b[1;31m')
                    e.problem_mark.name = repo.local(filepath)
                    print(e)
                    sys.stdout.write('\x1b[0m')


def process_patch(patch, env):
    if isinstance(patch, list):
        return [process_patch(p, env) for p in patch]

    if isinstance(patch, dict):
        return {process_patch(k, env): process_patch(v, env)
                for k, v in patch.items()}

    if isinstance(patch, str):
        return patch.format(ENV=env)

    return patch


repo = git.Git(path=os.path.join(args.storage_dir, 'repo'),
               repo=args.repo,
               key_file=args.deploy_key)

last_staging_file = os.path.join(args.storage_dir, 'last-staging')
last_production_file = os.path.join(args.storage_dir, 'last-production')
last_target_file = os.path.join(args.storage_dir, 'last-target')

repo.global_config(('user.name', args.user_name),
                   ('user.email', args.user_email))

last_staging_hash = read_scalar_from_path(last_staging_file)
last_production_hash = read_scalar_from_path(last_production_file)
last_target_hash = read_scalar_from_path(last_target_file)

waited_last_iter = False
first_iteration = True

while True:
    start_time = time.time()

    repo.fetch(args.staging_branch,
               args.production_branch,
               args.target_branch)

    current_staging_hash = repo.rev_list(args.staging_branch)
    current_production_hash = repo.rev_list(args.production_branch)
    current_target_hash = repo.rev_list(args.target_branch)

    staging_needs_update = (first_iteration or last_staging_hash is None or
                            last_staging_hash != current_staging_hash)

    production_needs_update = (first_iteration or last_production_hash is None
                               or last_production_hash !=
                                   current_production_hash)

    target_needs_update = (first_iteration or last_target_hash is None or
                           last_target_hash != current_target_hash)

    update_staging_hash = False
    update_production_hash = False
    update_target_hash = False

    all_up_to_date = not (staging_needs_update or
                          production_needs_update or
                          target_needs_update)

    if all_up_to_date and not waited_last_iter:
        log('Waiting for Updates')
        waited_last_iter = True

    if target_needs_update:
        waited_last_iter = False
        if current_target_hash != '-':
            log('Syncing Target Branch')
            repo.hard_sync(args.target_branch)
        update_target_hash = True

    if production_needs_update:
        waited_last_iter = False
        entries_map['production'] = {}
        special_map['production'] = {}

        if current_production_hash != '-':
            log('Syncing Production Branch')
            repo.hard_sync(args.production_branch)

            log('Processing Production Manifests')
            manifests = iter_manifests(
                    os.path.join(repo.path, args.source_dir),
                    repo,
                    'production')
            for entry in manifests:
                pass
            print('(done)')
        update_production_hash = True

    if staging_needs_update:
        waited_last_iter = False
        entries_map['staging'] = {}
        special_map['staging'] = {}

        if current_staging_hash != '-':
            log('Syncing Staging Branch')
            repo.hard_sync(args.staging_branch)

            log('Processing Staging Manifests')
            manifests = iter_manifests(os.path.join(repo.path, args.source_dir),
                                       repo,
                                       'staging')
            for entry in manifests:
                pass
            print('(done)')
        update_staging_hash = True

    if production_needs_update or staging_needs_update:
        log('Checking Out Target Branch')
        if current_target_hash == '-':
            repo('checkout', '-b', args.target_branch)
        else:
            repo.hard_sync(args.target_branch)

        # initial house keeping
        repo.clear_dir(os.path.join(repo.path, args.target_dir, 'production'))
        repo.clear_dir(os.path.join(repo.path, args.target_dir, 'staging'))

        log('Generating Production Manifests')

        # main production section
        target_infix = 'production'
        for entry in entries_map['production'].values():
            if entry.ignored:
                continue

            filename = '.'.join((
                            '-'.join((entry.api_group,
                                      entry.api_version,
                                      entry.kind,
                                      entry.namespace,
                                      entry.name)),
                            'yaml'))

            filepath = os.path.join(
                    repo.path, args.target_dir, target_infix, filename)

            print(f'  + {repo.local(filepath, infix=target_infix)}')
            with open(filepath, 'w') as f:
                f.write('---\n')
                yaml.dump(entry.obj, f)
            repo.add(filepath)

        log('Committing Production Manifests')
        repo.commit(f'update from production: {current_production_hash}')

        log('Generating Staging Manifests')

        # staging section
        target_infix = 'staging'
        for entry in special_map['staging'].values():
            if entry.ignored:
                continue

            tokens = entry.obj['data']['apiVersion'].split('/')
            api_group, api_version = (
                    ('builtin', tokens[0]) if len(tokens) == 1 else tokens)
            kind = entry.obj['data']['kind']
            name = entry.obj['data']['name']
            namespace = entry.namespace

            ref = entries_map['staging'].get(
                    (api_group, api_version, kind, namespace, name), None)

            if not ref:
                resource = '-'.join((
                    api_group, api_version, kind, namespace, name))
                warn(f'referenced resource not found: {resource}')
                continue

            try:
                patch = process_patch(
                        yaml.full_load(entry.obj['data']['patch']),
                        env='staging')
            except yaml.scanner.ScannerError as e:
                f_entry = '/'.join((entry.namespace, entry.name))
                warn(f'failed to parse patch data: {f_entry}')
                sys.stdout.write('\x1b[1;31m')
                print(e)
                sys.stdout.write('\x1b[0m')
                continue

            new_obj = copy.deepcopy(ref.obj)
            apply_patch(new_obj, patch)
            new_obj = ParsedEntry(new_obj, 'staging', update=False)

            if new_obj.ignored:
                continue

            filename = '.'.join((
                            '-'.join((new_obj.api_group,
                                      new_obj.api_version,
                                      new_obj.kind,
                                      new_obj.namespace,
                                      new_obj.name)),
                            'yaml'))


            filepath = os.path.join(
                    repo.path, args.target_dir, target_infix, filename)

            print(f'  + {repo.local(filepath, infix=target_infix)}')
            with open(filepath, 'w') as f:
                f.write('---\n')
                yaml.dump(new_obj.obj, f)
            repo.add(filepath)

        log('Committing Staging Manifests')
        repo.commit(f'update from staging: {current_staging_hash}')

        log('Pushing Updates')
        repo.push(args.target_branch, args.target_branch)

        current_target_hash = repo.rev_list(args.target_branch)
        update_staging_hash = True
        update_production_hash = True
        update_target_hash = True

    if update_staging_hash:
        write_scalar_to_path(last_staging_file, current_staging_hash)
        last_staging_hash = current_staging_hash

    if update_production_hash:
        write_scalar_to_path(last_production_file, current_production_hash)
        last_production_hash = current_production_hash

    if update_target_hash:
        write_scalar_to_path(last_target_file, current_target_hash)
        last_target_hash = current_target_hash

    elapsed_time = time.time() - start_time
    sleep_time = args.interval - elapsed_time
    if sleep_time > 0:
        time.sleep(sleep_time)

    first_iteration = False
