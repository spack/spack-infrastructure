#!/usr/bin/env python

import boto3


if __name__ == '__main__':
    iam = boto3.resource('iam')
    group = iam.Group('Administrators')
    for user in group.users.all():
        for access_key in user.access_keys.all():
            access_key.delete()
    print('Access keys cleared')
