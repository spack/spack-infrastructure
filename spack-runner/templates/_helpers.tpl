{{- define "config.toml" -}}
[[runners]]
    pre_build_script = """
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
    """

    output_limit = 10240
    environment = ["FF_GITLAB_REGISTRY_HELPER_IMAGE=1"]

    [runners.kubernetes]
    {{- if .Values.helperImage -}}
    helper_image = {{- .Values.helperImage -}}
    {{ end }}
    privileged = false
    helper_memory_request = "512m"

    cpu_request = "750m"
    cpu_request_overwrite_max_allowed = "16"

    memory_request = "2G"
    memory_request_overwrite_max_allowed = "64G"
    memory_limit = "64G"
    memory_limit_overwrite_max_allowed = "64G"

    namespace = "pipeline"
    poll_timeout = 600  # ten minutes
    service_account = "runner"

    [runners.kubernetes.pod_annotations]
        "fluentbit.io/exclude" = "true"
        "karpenter.sh/do-not-evict" = "true"
        "gitlab/ci_pipeline_url" = "$CI_PIPELINE_URL"
        "gitlab/ci_job_url" = "$CI_JOB_URL"
        "gitlab/ci_project_url" = "$CI_PROJECT_URL"
        "gitlab/ci_runner_description" = "$CI_RUNNER_DESCRIPTION"
        "gitlab/ci_job_id" = "$CI_JOB_ID"
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
        "metrics/spack_job_spec_pkg_version" = "$SPACK_JOB_SPEC_PKG_VERSION"
        "metrics/spack_job_spec_compiler_name" = "$SPACK_JOB_SPEC_COMPILER_NAME"
        "metrics/spack_job_spec_compiler_version" = "$SPACK_JOB_SPEC_COMPILER_VERSION"
        "metrics/spack_job_spec_arch" = "$SPACK_JOB_SPEC_ARCH"
        "metrics/spack_job_spec_variants" = "$SPACK_JOB_SPEC_VARIANTS"
        "metrics/spack_spec_needs_rebuild" = "$SPACK_SPEC_NEEDS_REBUILD"

    [[runners.kubernetes.volumes.secret]]
        name = "spack-intermediate-ci-signing-key"
        mount_path = "/mnt/key/"
        read_only = true

    {{ if .Values.additionalRunnerConfig }}
    {{- .Values.additionalRunnerConfig -}}
    {{- end -}}

{{- end -}}
