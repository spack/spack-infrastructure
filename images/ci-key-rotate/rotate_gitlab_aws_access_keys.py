#!/usr/bin/env python

import boto3
import os
import urllib.parse
import urllib.request


def update_gitlab_variable(k, v):
    DATA = urllib.parse.urlencode({'value': v}).encode()
    URL = 'https://gitlab.spack.io/api/v4/projects/2/variables/{0}'.format(k)
    request = urllib.request.Request(url=URL, data=DATA, method='PUT')
    request.add_header('Authorization', 'Bearer %s' % os.environ['GITLAB_TOKEN'])
    urllib.request.urlopen(request)


def rotate_iam_keys(iam_user, gitlab_variable_prefix='', protected=True):
    print('Begin IAM key rotation for user "{0}"'.format(iam_user))

    # Get existing keys.
    print('Querying AWS IAM for access keys')
    iam = boto3.client('iam')
    paginator = iam.get_paginator('list_access_keys')
    for response in paginator.paginate(UserName=iam_user):
        access_keys = response['AccessKeyMetadata']
        num_keys = len(access_keys)
        if num_keys < 2:
            raise Exception('Expected to find 2 keys for {0}, found {1} instead.'.format(iam_user, num_keys))

    # Figure out which of the two access keys is older.
    old_key = None
    if access_keys[0]['CreateDate'] < access_keys[1]['CreateDate']:
        old_key = access_keys[0]
    else:
        old_key = access_keys[1]

    # Delete the old key. It should be safe to do so at this point because it
    # hasn't been used by GitLab since the previous run of this script.
    print('Deleting old IAM access key')
    iam.delete_access_key(
        UserName=iam_user,
        AccessKeyId=old_key['AccessKeyId'])

    # Create a new IAM access key.
    print('Creating new IAM access key')
    response = iam.create_access_key(UserName=iam_user)
    new_key = response['AccessKey']

    # Update GitLab to use this new key.
    print('Updating GitLab to use new IAM access key')

    gitlab_secret_key = '{0}MIRRORS_AWS_SECRET_ACCESS_KEY'.format(gitlab_variable_prefix)
    gitlab_secret_value = new_key['SecretAccessKey']
    update_gitlab_variable(gitlab_secret_key, gitlab_secret_value)

    gitlab_access_id_key = '{0}MIRRORS_AWS_ACCESS_KEY_ID'.format(gitlab_variable_prefix)
    gitlab_access_id_value = new_key['AccessKeyId']
    update_gitlab_variable(gitlab_access_id_key, gitlab_access_id_value)

    print('IAM key rotation for user "{0}" complete!'.format(iam_user))


if __name__ == '__main__':
    if 'GITLAB_TOKEN' not in os.environ:
        raise Exception('GITLAB_TOKEN environment is not set')

    rotate_iam_keys('pull-requests-binary-mirror', gitlab_variable_prefix='PR_')
    rotate_iam_keys('protected-binary-mirror', gitlab_variable_prefix='PROTECTED_')
    rotate_iam_keys('cray-binary-mirror', gitlab_variable_prefix='CRAY_')
    rotate_iam_keys('develop-binary-mirror')
