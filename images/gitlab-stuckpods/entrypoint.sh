#!/usr/bin/env bash

command -v curl &> /dev/null || { echo "curl required, exiting."; exit 1; }
command -v jq &> /dev/null || { echo "jq required, exiting."; exit 1; }
command -v parallel &> /dev/null || { echo "parallel required, exiting."; exit 1; }
command -v kubectl &> /dev/null || { echo "kubectl required, exiting."; exit 1; }

read -r -d '' JQ_PROG <<'EOF'
.data[] | select(.labels.alertname=="GitlabPipelinePodStuck") | .labels.pod
EOF

pod_names () {
    curl -s http://kube-prometheus-stack-alertmanager.monitoring:9093/api/v1/alerts | jq -r "$JQ_PROG"
}


while true
do
    echo "[$(date)] Checking for pods..."
    for name in $(pod_names); do
        if  kubectl get pod/${name} -n pipeline > /dev/null 2>&1; then
            kubectl delete pod/${name} -n pipeline > /dev/null 2>&1
            echo "[$(date)]   deleted: $name."
        fi
    done

    # 5 Minutes
    sleep 300;
done
