local runners = import '../../../lib/runners.libsonnet';
std.manifestYamlStream(runners.linuxX86(
  name='runner-x86-v4-prot', tier='protected',
  requiredValues=['v4'], preferred=[], podWeight=1,
  tags='x86_64,x86_64_v2,x86_64_v3,x86_64_v4,avx,avx2,avx512,small,medium,large,huge,protected,aws,spack',
))
