local runners = import '../../../lib/runners.libsonnet';
std.manifestYamlStream(runners.windows(
  name='runner-x86-v2-pub-windows', tier='public',
  tags='spack,public,small,medium,win64,x86_64-win,x86_64_v2-win,aws',
))
