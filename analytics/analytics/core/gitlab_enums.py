"""Integer enums used by GitLab's own database schema.

These are read directly out of the GitLab database (as opposed to the webhook
payloads, which already contain the string forms), so we need GitLab's mapping
from integer to name. They change rarely, but they are GitLab's to define -- if
a pipeline reports an unknown value, consult the upstream source below.
"""

# Taken from https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/concerns/enums/ci/commit_status.rb
# It's possible this changes slightly in the future, but for our purposes, it probably won't.
FAILURE_REASON_MAP = {
    None: "unknown_failure",
    1: "script_failure",
    2: "api_failure",
    3: "stuck_or_timeout_failure",
    4: "runner_system_failure",
    5: "missing_dependency_failure",
    6: "runner_unsupported",
    7: "stale_schedule",
    8: "job_execution_timeout",
    9: "archived_failure",
    10: "unmet_prerequisites",
    11: "scheduler_failure",
    12: "data_integrity_failure",
    13: "forward_deployment_failure",  # Deprecated in favor of failed_outdated_deployment_job.
    14: "user_blocked",
    15: "project_deleted",
    16: "ci_quota_exceeded",
    17: "pipeline_loop_detected",
    18: "no_matching_runner",
    19: "trace_size_exceeded",
    20: "builds_disabled",
    21: "environment_creation_failure",
    22: "deployment_rejected",
    23: "failed_outdated_deployment_job",
    1_000: "protected_environment_failure",
    1_001: "insufficient_bridge_permissions",
    1_002: "downstream_bridge_project_not_found",
    1_003: "invalid_bridge_trigger",
    1_004: "upstream_bridge_project_not_found",
    1_005: "insufficient_upstream_permissions",
    1_006: "bridge_pipeline_is_child_pipeline",  # not used anymore, but cannot be deleted because of old data
    1_007: "downstream_pipeline_creation_failed",
    1_008: "secrets_provider_not_found",
    1_009: "reached_max_descendant_pipelines_depth",
    1_010: "ip_restriction_failure",
    1_011: "reached_max_pipeline_hierarchy_size",
    1_012: "reached_downstream_pipeline_trigger_rate_limit",
    1_013: "duo_workflow_not_allowed",
}

# https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/ci/runner.rb?ref_type=heads#L43-47
RUNNER_TYPE_MAP = {
    1: "instance_type",
    2: "group_type",
    3: "project_type",
}
