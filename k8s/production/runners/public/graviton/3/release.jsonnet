local runners = import '../../../lib/runners.libsonnet';
std.manifestYamlStream(runners.linuxGraviton(
  name='runner-graviton3-pub', tier='public', generation='3',
  helperImage='registry.gitlab.com/gitlab-org/gitlab-runner/gitlab-runner-helper:arm-latest',
  tags='arm,aarch64,graviton,graviton3,neoverse_v1,small,medium,large,huge,public,aws,spack',
))
