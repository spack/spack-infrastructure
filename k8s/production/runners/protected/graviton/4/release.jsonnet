local runners = import '../../../lib/runners.libsonnet';
std.manifestYamlStream(runners.linuxGraviton(
  name='runner-graviton4-prot', tier='protected', generation='4',
  helperImage='registry.gitlab.com/gitlab-org/gitlab-runner/gitlab-runner-helper:arm64-latest',
  tags='arm,aarch64,graviton4,neoverse_v2,small,medium,large,huge,protected,aws,spack',
))
