#!/usr/bin/env bash

command -v curl &> /dev/null || { echo "curl required, exiting."; exit 1; }
command -v jq &> /dev/null || { echo "jq required, exiting."; exit 1; }
command -v kubectl &> /dev/null || { echo "kubectl required, exiting."; exit 1; }

# Build pods live in `pipeline` (public/signing) or `pipeline-protected` (protected), so the
# alert's `source_namespace` label decides where to look rather than a hardcoded namespace.
read -r -d '' JQ_PROG <<'EOF'
.data[]
  | select(.labels.alertname=="GitlabPipelinePodStuck")
  | select(.labels.source_namespace != null and .labels.source_namespace != "")
  | "\(.labels.source_namespace) \(.labels.pod)"
EOF

stuck_pods () {
    curl -s http://kube-prometheus-stack-alertmanager.monitoring:9093/api/v1/alerts | jq -r "$JQ_PROG"
}


while true
do
    echo "[$(date)] Checking for pods..."
    while read -r namespace name; do
        [ -n "$name" ] || continue
        if  kubectl get pod/${name} -n ${namespace} > /dev/null 2>&1; then
            kubectl delete pod/${name} -n ${namespace} > /dev/null 2>&1
            echo "[$(date)]   deleted: ${namespace}/${name}."
        fi
    done < <(stuck_pods)

    # 5 Minutes
    sleep 300;
done
