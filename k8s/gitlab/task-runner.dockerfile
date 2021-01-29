FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-task-runner-ee:v13.8.0

RUN sed -i -e 's/LOW_NEEDS_LIMIT = [0-9]\+/LOW_NEEDS_LIMIT = 1000/g' \
           -e 's/HARD_NEEDS_LIMIT = [0-9]\+/HARD_NEEDS_LIMIT = 1000/g' \
               /srv/gitlab/lib/gitlab/ci/pipeline/seed/build.rb \
 && ss='s/return false unless Feature.enabled?(:ci_yaml_limit_size.*' \
  ; ss="$ss/return false/g" \
 && sed -i \
        -e 's/MAX_YAML_SIZE = 1\.megabyte\+/MAX_YAML_SIZE = 1024\.megabyte/g' \
        -e "$ss" /srv/gitlab/lib/gitlab/config/loader/yaml.rb
