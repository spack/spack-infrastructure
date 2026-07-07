#!/usr/bin/env python

import boto3
import sentry_sdk

sentry_sdk.init(
    # This cron job runs infrequently, so just record all transactions.
    traces_sample_rate=1.0,
)

if __name__ == '__main__':
    iam = boto3.resource('iam')
    group = iam.Group('Custodians')
    for user in group.users.all():
        for access_key in user.access_keys.all():
            access_key.delete()
    print('Access keys cleared')
