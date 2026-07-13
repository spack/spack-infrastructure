local runners = import '../../../lib/runners.libsonnet';
std.manifestYamlStream(runners.linuxX86(
  name='runner-x86-v2-prot', tier='protected',
  requiredValues=['v2', 'v3', 'v4'],
  preferred=[{ weight: 3, value: 'v2' }, { weight: 2, value: 'v3' }, { weight: 1, value: 'v4' }],
  tags='x86_64,x86_64_v2,small,medium,large,huge,protected,aws,spack',
))
