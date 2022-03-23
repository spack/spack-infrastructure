# Mitigation of "stuck" pods

For reasons that continue to be unclear,  sometimes gitlab job pods become "stuck." Stuck here refers to Pods that should have been terminated due to Job success, failure or timeout but for whatever reason are still hanging around with an open tty waiting for the helper container to feed them new commands.  

**This is problematic because running pods that are doing nothing prevent cluster autoscaler from cleaing up nodes which costs money.**

## How do we determine "stuck" pods?

Stuck pods are pods for which there has been no change in CPU, RAM or network traffic for more than (roughly) five minutes. Prometheus is configured with the `node_namespace_pod_name:pipline_stuck_pods_info` metric which identifies these pods in the pipeline namespace and generates the `GitlabPipelinePodStuck` alert.  This controller queries the alertmanager API every 5 minutes for pods triggering these alerts and removes them. 

## Related Gitlab Issue (?)

+ https://gitlab.com/gitlab-org/gitlab-runner/-/issues/25378


