{{/*
The GitLab runner `config.toml`, authored once for every runner type.

The gitlab-runner chart passes `.Values.runners.config` through `tpl` before
writing it to its ConfigMap, and Helm shares named templates between a chart
and its subcharts. So `values.yaml` only has to hook this template in:

    public:
      runners:
        config: '{{ include "spack.runnerConfig" . }}'

and it is rendered from the *subchart's* context. That means:

  .Values.spack.*        values for one visibility  (public / protected)
  .Values.global.spack.* values shared by the whole runner type

Keep this in sync with the Windows and signing runners, which are still
standalone HelmReleases under k8s/production/runners/.
*/}}

{{/*
The body of the pre-build script. Split out so the CI_OIDC_REQUIRED guard
below can wrap it without duplicating it.
*/}}
{{- define "spack.preBuildBody" -}}
echo 'Executing Spack pre-build setup script'

for cmd in "${PY3:-}" python3 python; do
  if command -v > /dev/null "$cmd"; then
    export PY3="$(command -v "$cmd")"
    break
  fi
done

if [ -z "${PY3:-}" ]; then
  echo "Unable to find python3 executable"
  exit 1
fi

$PY3 -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/spack/spack-infrastructure/main/scripts/gitlab_runner_pre_build/pre_build.py', 'pre_build.py')"
$PY3 pre_build.py > envvars

. ./envvars
rm -f envvars
unset GITLAB_OIDC_TOKEN
{{- end -}}

{{- define "spack.runnerConfig" -}}
{{- $s := .Values.global.spack -}}
[[runners]]
  pre_build_script = """
{{- /* `indent` pads blank lines too; strip that back out so the string stays
       free of trailing whitespace and YAML can emit it as a block scalar. */}}
{{- if .Values.spack.oidcOptional }}
  if [ ${CI_OIDC_REQUIRED:-1} == 1 ]; then
{{ include "spack.preBuildBody" . | indent 4 | replace "\n    \n" "\n\n" }}
  fi
{{- else }}
{{ include "spack.preBuildBody" . | indent 2 | replace "\n  \n" "\n\n" }}
{{- end }}
  """

  output_limit = 20480
  environment = ["FF_GITLAB_REGISTRY_HELPER_IMAGE=1"]
  [runners.kubernetes]
{{- if $s.helperImage }}
    helper_image = "{{ $s.helperImage }}"
{{- end }}
    privileged = false
    helper_memory_request = "512M"

    cpu_request = "750m"
    cpu_request_overwrite_max_allowed = "16"
    cpu_limit_overwrite_max_allowed = "{{ .Values.spack.cpuLimitMax }}"

    memory_request = "2G"
    memory_request_overwrite_max_allowed = "64G"
    memory_limit = "96G"
    memory_limit_overwrite_max_allowed = "96G"

    namespace = "pipeline"
    poll_timeout = 600  # ten minutes
    service_account = "runner"

    [runners.kubernetes.affinity]
      [runners.kubernetes.affinity.node_affinity]

      # {{ $s.nodeAffinityComment }}
      [runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution]
        [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms]]
          [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms.match_expressions]]
              key = "{{ required "global.spack.nodeLabelKey is required" $s.nodeLabelKey }}"
              operator = "In"
              values = [{{ range $i, $v := required "global.spack.schedulesOn is required" $s.schedulesOn }}{{ if $i }}, {{ end }}"{{ $v }}"{{ end }}]
          [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms.match_expressions]]
              key = "spack.io/pipeline"
              operator = "Exists"
{{- if $s.nodePreferences }}

      # Weight this pod towards {{ $s.preferenceComment }} nodes
{{- range $s.nodePreferences }}
      [[runners.kubernetes.affinity.node_affinity.preferred_during_scheduling_ignored_during_execution]]
          weight = {{ .weight }}
          [[runners.kubernetes.affinity.node_affinity.preferred_during_scheduling_ignored_during_execution.preference.match_expressions]]
            key = "{{ $s.nodeLabelKey }}"
            operator = "In"
            values = ["{{ .value }}"]
{{- end }}
{{- end }}

      # Place pod close to other pipeline pods if possible ("pack" the pods tightly)
{{- if .Values.spack.podAffinityNote }}
      # This takes precedence over the above weights, prioritizing pod packing
{{- end }}
      # Docs: https://docs.gitlab.com/runner/executors/kubernetes.html#define-nodes-where-pods-are-scheduled
      [runners.kubernetes.affinity.pod_affinity]
        [[runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution]]
        weight = {{ $s.podAffinityWeight }}
        [runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term]
          topology_key = "topology.kubernetes.io/zone"
          [runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term.label_selector]
            [[runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term.label_selector.match_expressions]]
              key = "spack.io/runner"
              operator = "In"
              values = ["true"]

    [runners.kubernetes.node_tolerations]
      "spack.io/runner-taint=true" = "NoSchedule"

    [runners.kubernetes.pod_annotations]
      "pod-cleanup.gitlab.com/ttl" = "12h"
      "fluentbit.io/exclude" = "true"
      "karpenter.sh/do-not-disrupt" = "true"
      "gitlab/ci_pipeline_url" = "$CI_PIPELINE_URL"
      "gitlab/ci_job_url" = "$CI_JOB_URL"
      "gitlab/ci_project_url" = "$CI_PROJECT_URL"
      "gitlab/ci_runner_description" = "$CI_RUNNER_DESCRIPTION"
      "gitlab/ci_job_id" = "$CI_JOB_ID"
      "metrics/spack_job_spec_pkg_name" = "$SPACK_JOB_SPEC_PKG_NAME"
      "metrics/spack_job_spec_hash" = "$SPACK_JOB_SPEC_DAG_HASH"
      "metrics/spack_job_spec_pkg_version" = "$SPACK_JOB_SPEC_PKG_VERSION"
      "metrics/spack_job_spec_compiler_name" = "$SPACK_JOB_SPEC_COMPILER_NAME"
      "metrics/spack_job_spec_compiler_version" = "$SPACK_JOB_SPEC_COMPILER_VERSION"
      "metrics/spack_job_spec_arch" = "$SPACK_JOB_SPEC_ARCH"
      "metrics/spack_job_spec_variants" = "$SPACK_JOB_SPEC_VARIANTS"
      "metrics/spack_job_build_jobs" = "$SPACK_BUILD_JOBS"
      "metrics/spack_ci_stack_name" = "$SPACK_CI_STACK_NAME"
    [runners.kubernetes.pod_labels]
      "spack.io/runner" = "true"
      "gitlab/ci_job_id" = "$CI_JOB_ID"
      "gitlab/ci_job_size" = "$CI_JOB_SIZE"
      "metrics/gitlab_ci_pipeline_id" = "$CI_PIPELINE_ID"
      "metrics/gitlab_ci_project_namespace" = "$CI_PROJECT_NAMESPACE"
      "metrics/gitlab_ci_project_name" = "$CI_PROJECT_NAME"
      "metrics/gitlab_ci_job_stage" = "$CI_JOB_STAGE"
      "metrics/gitlab_ci_commit_ref_name" = "$CI_COMMIT_REF_NAME"
      "metrics/spack_ci_stack_name" = "$SPACK_CI_STACK_NAME"
      "metrics/spack_job_spec_pkg_name" = "$SPACK_JOB_SPEC_PKG_NAME"
      "metrics/spack_spec_needs_rebuild" = "$SPACK_SPEC_NEEDS_REBUILD"
{{- if .Values.spack.protected }}

    [[runners.kubernetes.volumes.secret]]
      name = "spack-intermediate-ci-signing-key"
      mount_path = "/mnt/key/"
      read_only = true
{{- end }}
{{- end -}}
