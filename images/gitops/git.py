import os
import subprocess
import shutil

class Git:
    def __init__(self, path, repo=None, key_file=None):
        self.repo = repo
        self.path = os.path.abspath(path)
        self.key_file = key_file
        if self.key_file is not None:
            self.key_file = os.path.abspath(self.key_file)

        ssh_command = ['ssh',
                       '-o', 'StrictHostKeyChecking=no',
                       '-o', 'UserKnownHostsFile=/dev/null']
        if self.key_file:
            ssh_command.extend(['-i', self.key_file])

        self.env = {}
        self.env.update(os.environ)
        self.env['GIT_SSH_COMMAND'] = ' '.join(ssh_command)


    def rev_list(self, branch):
        success, text = self(
                'rev-list', '-n', '1', f'origin/{branch}', '--',
                capture=True,
                stderr=subprocess.DEVNULL)
        if success:
            text = text.strip()
        else:
            text = '-'
        return text


    def hard_sync(self, branch):
        success, _ = self('checkout', branch)
        if success:
            success, _ = self('reset', '--hard', f'origin/{branch}')
        return success


    def clear_dir(self, path):
        if os.path.isdir(path):
            success, _ = self('rm', '-rf', self.local(path),
                    stderr=subprocess.DEVNULL)
            if not success:
                shutil.rmtree(path)
        os.makedirs(path)


    def global_config(self, *configs):
        for k, v in configs:
            self('config', '--global', k, v, raw=True)


    def fetch(self, *refs):
        if os.path.exists(self.path):
            for ref in refs:
                self('fetch', 'origin', ref,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
        else:
            os.makedirs(self.path)
            self('clone', self.repo, self.path, raw=True)


    def add(self, path):
        success, _ = self('add', self.local(path))
        return success


    def commit(self, message):
        success, _ = self('commit', '--allow-empty', '-m', message)
        return success


    def push(self, source_branch, target_branch):
        spec = ':'.join((source_branch, target_branch))
        success, _ = self('push', 'origin', spec)
        return success


    def local(self, path, infix=None):
        top = self.path
        if infix:
            top = os.path.join(top, infix)
        return os.path.relpath(path, top)


    def __call__(self, *args, **kwargs):
        raw = kwargs.pop('raw', False)
        capture = kwargs.pop('capture', False)

        new_env = {}
        new_env.update(self.env)
        new_env.update(kwargs.pop('env', {}))
        kwargs['env'] = new_env

        if not raw:
            args = ['-C', self.path] + list(args)
        args = ['git'] + list(args)

        success = False
        text = None
        try:
            if capture:
                text = subprocess.check_output(args, **kwargs).decode('UTF-8')
            else:
                subprocess.check_call(args, **kwargs)
            success = True
        except subprocess.CalledProcessError:
            pass

        return (success, text)
