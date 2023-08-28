#!/usr/bin/env bash
set -euo pipefail
DATETIME=$(date +%s)

# The build timing processor job template is used as a base, since it makes use of the
# "upload-build-timings" image, which contains the django app
cat images/build-timing-processor/job-template.yaml \
    | sed -e "s/build-timing-processing-job/analytics-db-run-migrations-$DATETIME/g" \
    | yq --output-format=yaml '.spec.template.spec.containers[0].command = ["./analytics/manage.py",  "migrate"]' \
    > job.yaml

# Apply the migration job and capture the job name
JOBNAME=$(kubectl apply -f job.yaml | sed -E 's/job.batch\/(.*) created/\1/')

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
