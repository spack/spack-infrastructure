local runners = import '../../../lib/runners.libsonnet';
std.manifestYamlStream(runners.linuxX86(
  name='runner-x86-v3-prot', tier='protected',
  requiredValues=['v3', 'v4'],
  preferred=[{ weight: 2, value: 'v3' }, { weight: 1, value: 'v4' }],
  tags='x86_64,x86_64_v2,x86_64_v3,avx,avx2,small,medium,large,huge,protected,aws,spack',
))
