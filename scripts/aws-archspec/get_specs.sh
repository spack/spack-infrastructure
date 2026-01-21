#!/usr/bin/env bash

# Preflight
hash terraform 2>/dev/null || { echo >&2 "terraform not installed.  Aborting."; exit 1; }
hash jq 2>/dev/null || { echo >&2 "jq not installed.  Aborting."; exit 1; }
hash parallel 2>/dev/null || { echo >&2 "parallel not installed.  Aborting."; exit 1; }
hash aws 2>/dev/null || { echo >&2 "aws CLI not installed.  Aborting."; exit 1; }


# Get the unique states of all instances status checks. When the instances are
# ready this should return a single (nonquoted) "ok".
function instance_states {
# Terraform output has a list of instance IDs. We pull these out of the
# terraform output then pass them to a parallel command that calls aws ec2
# describe-instances. We then pull out the InstanceStatus and SystemStatus
# check values,  sort and uniq them.
    terraform output -json instance_ids | \
        jq -r '.[]' | \
        parallel aws ec2 --region us-east-1 \
          describe-instance-status \
          --instance-ids {} \
          --query "InstanceStatuses[*].[InstanceStatus.Status,SystemStatus.Status]" \
          --output json | \
        jq -s -r '.[][][]' | sort | uniq

}

# Wait for the instances to actually be "OK." This means assuming everything
# else is correctly configured (e.g. security groups) we should be able to SSH
# into the instances.
if [ "$(instance_states)" != "ok" ]; then
    echo -n "Waiting for instances to be ready..." >&2
    while STATE=$(instance_states); test "$STATE" != "ok"; do sleep 2; echo -n '.'; done
    echo -n "(Done)" >&2; echo "" >&2
fi



# Set the SSH arguments for Gnu Parallel
export PARALLEL_SSH="ssh -o LogLevel=ERROR -o StrictHostKeyChecking=No -l ec2-user -i archspec-service-account.pem"

# Print the CSV output header
echo "id,instance_type,ami,archspec"

# SSH into each instance and run cat /instances.txt. Note that the "cluster"
# file is produced by the terraform and that "instance.txt" should exist on each
# instance after the user_data has completed running on EC2 instance
# initialization
parallel --slf cluster --nonall "cat /instance.txt"
