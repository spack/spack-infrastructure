local runners = import '../lib/runners.libsonnet';
std.manifestYamlStream(runners.signing(
  name='runner-spack-package-signing',
))
