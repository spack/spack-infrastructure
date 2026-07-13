// runners.libsonnet
//
// Shared library for all GitLab runner HelmReleases.
//
// Design: the runner `config` is kept as raw TOML in ||| string blocks (so the
// inline comments survive), but everything that repeats -- the HelmRepository,
// the HelmRelease skeleton, the shared TOML middle (annotations/labels/
// tolerations/pod_affinity), the pre-build scripts, and the signing-key volume
// -- lives here exactly once. Per-runner files only supply what actually differs.
//
// Each builder returns a list of Kubernetes objects; callers render with
// std.manifestYamlStream(...) to emit the two-document YAML stream.

{
  local runners = self,

  namespace:: 'gitlab',
  chartVersion:: '0.90.1',  // gitlab-runner@19.1.1
  prodGitlabUrl:: 'https://gitlab.spack.io/',

  // ---- small string helpers -------------------------------------------------

  // Indent every non-blank line of `s` by `pad` (blank lines stay empty).
  indent(s, pad):: std.join('\n', [
    if line == '' then '' else pad + line
    for line in std.split(std.rstripChars(s, '\n'), '\n')
  ]),

  // ---- pre-build scripts ----------------------------------------------------

  // The canonical Linux pre-build body, defined once. Kept as a first-class
  // shell script (`linux_pre_build.sh`) and inlined here via importstr so it can
  // be edited/linted as a real script; the trailing newline matches the old
  // ||| block, and indent()/linuxPreBuildOidc below still slot it into the TOML.
  local linuxPreBuildBody = importstr './linux_pre_build.sh',

  // Most runners run the body unconditionally (indented to sit under the TOML key).
  linuxPreBuild:: runners.indent(linuxPreBuildBody, '  '),

  // The `service`-tagged runner wraps the *same* body in the CI_OIDC_REQUIRED
  // guard -- the body is reused, not copy-pasted.
  linuxPreBuildOidc:: '  if [ ${CI_OIDC_REQUIRED:-1} == 1 ]; then\n'
                      + runners.indent(linuxPreBuildBody, '    ') + '\n'
                      + '  fi',

  // ---- shared TOML fragments ------------------------------------------------

  // The pod_affinity block ("pack" pipeline pods tightly); only `weight` varies.
  podAffinity(weight):: |||
        # Place pod close to other pipeline pods if possible ("pack" the pods tightly)
        # Docs: https://docs.gitlab.com/runner/executors/kubernetes.html#define-nodes-where-pods-are-scheduled
        [runners.kubernetes.affinity.pod_affinity]
          [[runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution]]
          weight = %d
          [runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term]
            topology_key = "topology.kubernetes.io/zone"
            [runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term.label_selector]
              [[runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term.label_selector.match_expressions]]
                key = "spack.io/runner"
                operator = "In"
                values = ["true"]
  ||| % weight,

  // x86_64 node affinity: gate on >= a minimum microarch, weight towards it.
  x86NodeAffinity(requiredValues, preferred)::
    '        # Schedule this pod on x86_64 node(s)\n'
    + '        [runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution]\n'
    + '          [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms]]\n'
    + '            [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms.match_expressions]]\n'
    + '                key = "spack.io/x86_64"\n'
    + '                operator = "In"\n'
    + '                values = [%s]\n' % std.join(', ', ['"%s"' % v for v in requiredValues])
    + '            [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms.match_expressions]]\n'
    + '                key = "spack.io/pipeline"\n'
    + '                operator = "Exists"\n'
    + std.join('', [
      '        [[runners.kubernetes.affinity.node_affinity.preferred_during_scheduling_ignored_during_execution]]\n'
      + '            weight = %d\n' % p.weight
      + '            [[runners.kubernetes.affinity.node_affinity.preferred_during_scheduling_ignored_during_execution.preference.match_expressions]]\n'
      + '              key = "spack.io/x86_64"\n'
      + '              operator = "In"\n'
      + '              values = ["%s"]\n' % p.value
      for p in preferred
    ]),

  // graviton node affinity: pin to exactly one graviton generation.
  gravitonNodeAffinity(generation)::
    '        # Schedule this pod on only graviton %s nodes\n' % generation
    + '        [runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution]\n'
    + '          [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms]]\n'
    + '            [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms.match_expressions]]\n'
    + '                key = "spack.io/graviton"\n'
    + '                operator = "In"\n'
    + '                values = ["%s"]\n' % generation
    + '            [[runners.kubernetes.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms.match_expressions]]\n'
    + '                key = "spack.io/pipeline"\n'
    + '                operator = "Exists"\n',

  // The signing-key volume, present only on protected + signing runners.
  signingKeyVolume:: |||

          [[runners.kubernetes.volumes.secret]]
            name = "spack-intermediate-ci-signing-key"
            mount_path = "/mnt/key/"
            read_only = true
  |||,

  // ---- config assembly ------------------------------------------------------

  // Assemble a Linux runner `config` TOML from its varying pieces.
  linuxConfig(
    preBuild,
    cpuLimitMax,
    nodeAffinity,
    podAffinityWeight,
    helperImage=null,
    secretVolume='',
  )::
    |||
      [[runners]]
        pre_build_script = """
    ||| + preBuild + '\n' + std.stripChars(|||
        """

        output_limit = 20480
        environment = ["FF_GITLAB_REGISTRY_HELPER_IMAGE=1"]
        [runners.kubernetes]
          privileged = false
          helper_memory_request = "512M"
    |||, '\n')
    + (if helperImage != null then '\n          helper_image = "%s"' % helperImage else '')
    + '\n' + std.strReplace(|||
          cpu_request = "750m"
          cpu_request_overwrite_max_allowed = "16"
          cpu_limit_overwrite_max_allowed = "__CPU_LIMIT__"

          memory_request = "2G"
          memory_request_overwrite_max_allowed = "64G"
          memory_limit = "96G"
          memory_limit_overwrite_max_allowed = "96G"

          namespace = "pipeline"
          poll_timeout = 600  # ten minutes
          service_account = "runner"

          [runners.kubernetes.affinity]
            [runners.kubernetes.affinity.node_affinity]
    |||, '__CPU_LIMIT__', cpuLimitMax)
    + nodeAffinity
    + '\n' + runners.podAffinity(podAffinityWeight)
    + std.stripChars(|||

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
    |||, '\n')
    + secretVolume,

  // ---- object builders ------------------------------------------------------

  helmRepository(name):: {
    apiVersion: 'source.toolkit.fluxcd.io/v1',
    kind: 'HelmRepository',
    metadata: { name: name, namespace: runners.namespace },
    spec: { interval: '10m', url: 'https://charts.gitlab.io' },
  },

  // The HelmRelease skeleton shared by every runner. `values` is merged over the
  // common defaults, `runnerValues` over the common `values.runners` block. The
  // named knobs cover the axes the signing runner needs to bend (image, pull
  // policy, probe timeout, memory request, whether a cache stanza is emitted).
  helmRelease(
    name,
    values={},
    runnerValues={},
    image='busybox:1.32.0',
    runnerImagePullPolicy='if-not-present',
    probeTimeout=70,
    memory='1G',
    cache=true,
    helpers=true,
  ):: {
    apiVersion: 'helm.toolkit.fluxcd.io/v2',
    kind: 'HelmRelease',
    metadata: { name: name, namespace: runners.namespace },
    spec: {
      interval: '10m',
      chart: {
        spec: {
          chart: 'gitlab-runner',
          version: runners.chartVersion,
          sourceRef: { kind: 'HelmRepository', name: name },
        },
      },
      dependsOn: [{ name: 'gitlab', namespace: 'gitlab' }],
      // See terraform/modules/sentry/sentry.tf
      valuesFrom: [
        { kind: 'ConfigMap', name: 'gitlab-runner-sentry-config', valuesKey: 'values.yaml' },
      ],
      values: {
        imagePullPolicy: 'IfNotPresent',
        [if probeTimeout != null then 'probeTimeoutSeconds']: probeTimeout,
        gitlabUrl: runners.prodGitlabUrl,
        unregisterRunners: true,
        terminationGracePeriodSeconds: 21600,  // six hours
        checkInterval: 30,
        metrics: { enabled: true },
        rbac: { serviceAccountName: 'runner' },
        nodeSelector: { 'spack.io/node-pool': 'base' },
        resources: {
          // sum by (pod) (container_memory_max_usage_bytes{namespace="gitlab", pod=~"runner-x86.*"})
          requests: { memory: memory },
        },
        podAnnotations: { 'karpenter.sh/do-not-disrupt': true },
        runners: {
          image: image,
          imagePullPolicy: runnerImagePullPolicy,
          runUntagged: false,
          secret: 'spack-group-runner-secret',
          [if cache then 'cache']: {},
          services: {},
          [if helpers then 'helpers']: {},
        } + runnerValues,
      } + values,
    },
  },

  // ---- high-level Linux runner ----------------------------------------------

  // The tier-dependent runner fields (locked/protected/serviceAccountName + tags),
  // shared by the Linux and Windows builders.
  tierRunnerValues(tier, tags, serviceAccount=(tier != 'public'))::
    {
      tags: tags,
      locked: tier != 'public',
      [if tier != 'public' then 'protected']: true,
      [if serviceAccount then 'serviceAccountName']: 'runner',
    },

  // tier: 'public' | 'protected'. `serviceAccount` defaults to protected-only, but
  // public graviton runners also set it, so it's overridable.
  linux(name, tier, tags, config, replicas=3, concurrent=40, serviceAccount=(tier != 'public'), helpers=true):: [
    runners.helmRepository(name),
    runners.helmRelease(
      name,
      values={ replicas: replicas, concurrent: concurrent },
      runnerValues={ config: config } + runners.tierRunnerValues(tier, tags, serviceAccount),
      helpers=helpers,
    ),
  ],

  // The signing-key volume rides on protected/signing (non-public) runners only.
  local secretVolumeFor(tier) = if tier == 'public' then '' else runners.signingKeyVolume,
  // `oidc` (the CI_OIDC_REQUIRED guard) is opt-in per runner -- today only the
  // service-tagged public x86-v2 runner uses it, not the public tier at large.
  local preBuild(oidc) = if oidc then runners.linuxPreBuildOidc else runners.linuxPreBuild,

  // x86_64 runner. `requiredValues` gates scheduling (>= a microarch); `preferred`
  // is a list of {weight, value} biasing towards lower microarchs.
  linuxX86(name, tier, requiredValues, preferred, tags, podWeight=4, oidc=false):: runners.linux(
    name, tier, tags,
    config=runners.linuxConfig(
      preBuild=preBuild(oidc),
      cpuLimitMax=if tier == 'public' then '24' else '32',
      nodeAffinity=runners.x86NodeAffinity(requiredValues, preferred),
      podAffinityWeight=podWeight,
      secretVolume=secretVolumeFor(tier),
    ),
  ),

  // graviton runner. Public: 3 replicas / concurrent 40; protected: 2 / 30.
  linuxGraviton(name, tier, generation, helperImage, tags):: runners.linux(
    name, tier, tags,
    config=runners.linuxConfig(
      preBuild=runners.linuxPreBuild,
      cpuLimitMax='32',
      nodeAffinity=runners.gravitonNodeAffinity(generation),
      podAffinityWeight=1,
      helperImage=helperImage,
      secretVolume=secretVolumeFor(tier),
    ),
    replicas=if tier == 'public' then 3 else 2,
    concurrent=if tier == 'public' then 40 else 30,
    serviceAccount=true,  // graviton runners set this on both tiers
    helpers=false,  // graviton originals omit the empty helpers stanza
  ),

  // ---- Windows runner -------------------------------------------------------
  // Windows shares little with Linux (PowerShell pre-build, pod_spec, windows
  // node selectors), so it gets its own config template but reuses the same
  // HelmRelease skeleton, pod_affinity, tier fields and signing-key wiring.

  // The signing key mounts at a Windows path on protected windows runners.
  windowsSigningKeyVolume:: |||

          [[runners.kubernetes.volumes.secret]]
            name = "spack-intermediate-ci-signing-key"
            mount_path = "C:\\key"
            read_only = true
  |||,

  windowsConfig(secretVolume=''):: |||
    [[runners]]
      pre_get_sources_script = """
      git config --global core.autocrlf true
      """

      pre_build_script = """
      Write-Output 'Executing Spack pre-build setup script'

      $py=(get-command -ErrorAction SilentlyContinue python)
      if ( -not $py ) {
        Write-Output 'Python was not found on the system. Add it to the PATH or install.'
        exit 1
      }

      $scriptPath = Join-Path $HOME 'pre_build.py'

      $wc = New-Object System.Net.WebClient
      $wc.DownloadFile('https://raw.githubusercontent.com/spack/spack-infrastructure/main/scripts/gitlab_runner_pre_build/pre_build.py', $scriptPath)

      & python $scriptPath | Out-File -FilePath 'envvars.ps1' -Encoding utf8
      if ($LASTEXITCODE -ne 0) {
        Write-Output "Prebuild script pre_build.py failed with exit code $LASTEXITCODE. See error above for more info"
        exit 1
      }

      ./envvars.ps1

      Remove-Item $scriptPath -Force
      Remove-Item 'envvars.ps1' -Force

      $env:GITLAB_OIDC_TOKEN = $null
      """

      shell = "powershell"
      executor = "kubernetes"
      output_limit = 20480

      # Ensure windows paths are used
      [runners.feature_flags]
        FF_USE_POWERSHELL_PATH_RESOLVER = true

      [runners.kubernetes]
        privileged = false
        helper_memory_request = "1"

        cpu_request = "750m"
        cpu_request_overwrite_max_allowed = "16"
        cpu_limit_overwrite_max_allowed = "24"

        memory_request = "2G"
        memory_request_overwrite_max_allowed = "64G"
        memory_limit = "96G"
        memory_limit_overwrite_max_allowed = "96G"

        namespace = "pipeline"
        # Allow 30 minutes for the pod to be ready. This is necessary because
        # the windows docker image can take a significantly long time to pull/boot.
        poll_timeout = 1800
        service_account = "runner"

        # Image for windows 2022, runner helper
        image = "mcr.microsoft.com/windows/servercore:ltsc2022"
        helper_image = "registry.gitlab.com/gitlab-org/gitlab-runner/gitlab-runner-helper:x86_64-v19.1.1-servercore21H2"

        ephemeral_storage_request = "500M"
        helper_ephemeral_storage_request = "500M"

        # Place pod close to other pipeline pods if possible ("pack" the pods tightly)
        # Docs: https://docs.gitlab.com/runner/executors/kubernetes.html#define-nodes-where-pods-are-scheduled
        [runners.kubernetes.affinity]
          [runners.kubernetes.affinity.pod_affinity]
            [[runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution]]
            weight = 1
            [runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term]
              topology_key = "topology.kubernetes.io/zone"
              [runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term.label_selector]
                [[runners.kubernetes.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution.pod_affinity_term.label_selector.match_expressions]]
                  key = "spack.io/runner"
                  operator = "In"
                  values = ["true"]

        [[runners.kubernetes.pod_spec]]
          ttlSecondsAfterFinished = "300" # 5 minutes
        [runners.kubernetes.pod_annotations]
          "fluentbit.io/exclude" = "true"
          "karpenter.sh/do-not-disrupt" = "true"
          "gitlab/ci_pipeline_url" = "$CI_PIPELINE_URL"
          "gitlab/ci_job_url" = "$CI_JOB_URL"
          "gitlab/ci_project_url" = "$CI_PROJECT_URL"
          "gitlab/ci_runner_description" = "$CI_RUNNER_DESCRIPTION"
          "gitlab/ci_job_id" = "$CI_JOB_ID"
        [runners.kubernetes.pod_labels]
          "spack.io/runner" = "true"
          "gitlab/ci_job_size" = "$CI_JOB_SIZE"
          "metrics/gitlab_ci_pipeline_id" = "$CI_PIPELINE_ID"
          "metrics/gitlab_ci_project_namespace" = "$CI_PROJECT_NAMESPACE"
          "metrics/gitlab_ci_project_name" = "$CI_PROJECT_NAME"
          "metrics/gitlab_ci_job_stage" = "$CI_JOB_STAGE"
          "metrics/gitlab_ci_commit_ref_name" = "$CI_COMMIT_REF_NAME"
          "metrics/spack_ci_stack_name" = "$SPACK_CI_STACK_NAME"
          "metrics/spack_job_spec_pkg_name" = "$SPACK_JOB_SPEC_PKG_NAME"
          "metrics/spack_job_spec_hash" = "$SPACK_JOB_SPEC_DAG_HASH"
          "metrics/spack_spec_needs_rebuild" = "$SPACK_SPEC_NEEDS_REBUILD"
        [runners.kubernetes.node_selector]
          "kubernetes.io/os" = "windows"
          # This is required to match the helper image based on this table
          # https://gitlab.com/gitlab-org/gitlab-runner/-/blob/main/helpers/container/windows/version.go?ref_type=heads#L19-32
          "node.kubernetes.io/windows-build" = "10.0.20348"
        [runners.kubernetes.node_tolerations]
          "spack.io/runner-taint=true" = "NoSchedule"
          "windows=true" = "NoSchedule"
  ||| + secretVolume,

  // The public windows runner has two incidental wording/whitespace differences
  // from the protected template; apply them so it reproduces its original exactly.
  local windowsPublicize(s) = std.strReplace(
    std.strReplace(s, 'Python was not found on the system.', 'Python not found on the system.'),
    '  }\n\n  ./envvars.ps1',
    '  }\n  ./envvars.ps1',
  ),

  windows(name, tier, tags):: [
    runners.helmRepository(name),
    runners.helmRelease(
      name,
      values={ replicas: 3, concurrent: 40 },
      runnerValues={
        local cfg = runners.windowsConfig(
          if tier == 'public' then '' else runners.windowsSigningKeyVolume
        ),
        config: if tier == 'public' then windowsPublicize(cfg) else cfg,
      } + runners.tierRunnerValues(tier, tags),
      image='mcr.microsoft.com/windows/servercore:ltsc2022',
    ),
  ],

  // ---- signing runner -------------------------------------------------------
  // A one-off: notary image + service account, its own resources and volumes.
  // Still reuses the pre-build script, x86 node affinity and pod_affinity.

  signingConfig::
    std.stripChars(|||
      [[runners]]
        pre_build_script = """
    |||, '\n') + '\n' + runners.linuxPreBuild + '\n' + std.stripChars(|||
        """

        output_limit = 20480
        environment = ["FF_GITLAB_REGISTRY_HELPER_IMAGE=1"]
        [runners.kubernetes]
          privileged = false
          helper_memory_request = "512M"

          cpu_request = "10"
          cpu_limit = "10"
          memory_request = "8G"
          memory_limit = "64G"
          namespace = "pipeline"
          poll_timeout = 600  # ten minutes
          service_account = "notary"

          allowed_images = ["ghcr.io/spack/notary:*", "ghcr.io/spack/notary@*"]
          allowed_services = [""]

          [runners.kubernetes.affinity]
            [runners.kubernetes.affinity.node_affinity]
    |||, '\n') + '\n'
    + runners.x86NodeAffinity(['v3', 'v4'], [{ weight: 2, value: 'v3' }, { weight: 1, value: 'v4' }])
    + '\n' + runners.podAffinity(4)
    + std.stripChars(|||

          [runners.kubernetes.node_tolerations]
            "spack.io/notary-taint=true" = "NoSchedule"

          [runners.kubernetes.pod_annotations]
            "pod-cleanup.gitlab.com/ttl" = "7h"
            "fluentbit.io/exclude" = "true"
            "karpenter.sh/do-not-disrupt" = "true"
            "gitlab/ci_pipeline_url" = "$CI_PIPELINE_URL"
            "gitlab/ci_job_url" = "$CI_JOB_URL"
            "gitlab/ci_project_url" = "$CI_PROJECT_URL"
            "gitlab/ci_runner_description" = "$CI_RUNNER_DESCRIPTION"
            "gitlab/ci_job_id" = "$CI_JOB_ID"
          [runners.kubernetes.pod_labels]
            "spack.io/runner" = "true"
            "gitlab/ci_job_id" = "$CI_JOB_ID"
            "metrics/gitlab_ci_pipeline_id" = "$CI_PIPELINE_ID"
            "metrics/gitlab_ci_project_namespace" = "$CI_PROJECT_NAMESPACE"
            "metrics/gitlab_ci_project_name" = "$CI_PROJECT_NAME"
            "metrics/gitlab_ci_job_stage" = "$CI_JOB_STAGE"
            "metrics/gitlab_ci_commit_ref_name" = "$CI_COMMIT_REF_NAME"
            "metrics/spack_ci_stack_name" = "$SPACK_CI_STACK_NAME"
          [runners.kubernetes.node_selector]
            "kubernetes.io/arch" = "amd64"

          [[runners.kubernetes.volumes.secret]]
            name = "spack-signing-key-encrypted"
            mount_path = "/mnt/keys/signing"
            read_only = true

          [[runners.kubernetes.volumes.empty_dir]]
            name = "gnupg"
            mount_path = "/mnt/gnupg"
            medium = "Memory"
    |||, '\n'),

  signing(name):: [
    runners.helmRepository(name),
    runners.helmRelease(
      name,
      values={ replicas: 1, concurrent: 20 },
      runnerValues={ config: runners.signingConfig }
                   // signing sets its service account in-config (notary), not here.
                   + runners.tierRunnerValues('protected', 'spack,notary,aws,protected', serviceAccount=false),
      image='ghcr.io/spack/notary:0.0.4',
      runnerImagePullPolicy='always',
      probeTimeout=null,  // signing omits probeTimeoutSeconds
      memory='500M',
      cache=false,  // signing omits the cache stanza
    ),
  ],
}
