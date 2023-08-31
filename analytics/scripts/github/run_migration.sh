#!/usr/bin/env bash
set -euo pipefail
DATETIME=$(date +%s)

# Apply the migration job and capture the job name
JOBNAME=$(kubectl apply -f analytics/scripts/github/job.yaml | sed -E 's/job.batch\/(.*) created/\1/')

# Buffer for 2 seconds
sleep 2

# Wait for job to finish
RESULT=""
while [ -z "$RESULT" ]
do
    RESULT=$(kubectl get job -n default $JOBNAME -o jsonpath='{.status.conditions[0].type}')
done

# Check if job status is failed
if [ "$RESULT" -ne "Complete"]; then
    echo "Job $JOBNAME finished with unsuccessful status $RESULT"
    exit 1
fi
