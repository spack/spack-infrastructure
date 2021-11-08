FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-task-runner-ee@sha256:c643675862fc5b3dac0a75329ddd12cba51fef2e50e5fbc69a5f14e1b7af0b92

RUN ss='s/return false unless Feature.enabled?(:ci_yaml_limit_size.*' \
  ; ss="$ss/return false/g" \
 && sed -i \
        -e 's/MAX_YAML_SIZE = 1\.megabyte\+/MAX_YAML_SIZE = 1024\.megabyte/g' \
        -e "$ss" /srv/gitlab/lib/gitlab/config/loader/yaml.rb
