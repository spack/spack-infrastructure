FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-toolbox-ee:v14.6.3

RUN ss='s/return false unless Feature.enabled?(:ci_yaml_limit_size.*' \
  ; ss="$ss/return false/g" \
 && sed -i \
        -e 's/MAX_YAML_SIZE = 1\.megabyte\+/MAX_YAML_SIZE = 1024\.megabyte/g' \
        -e "$ss" /srv/gitlab/lib/gitlab/config/loader/yaml.rb
