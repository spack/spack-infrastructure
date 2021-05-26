FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-webservice-ee:v13.8.7

# TODO(opadron): At some point, we might want to reinvestigate gitlab code
# changes as a means of working around certain limits.  If/when we do, here are
# some spots that we had identified as potential targets for modifications:
#
# /srv/gitlab/lib/gitlab/ci:
#
#   config/entry/needs.rb:
#     NEEDS_CROSS_PIPELINE_DEPENDENCIES_LIMIT = 5
#
#   config/entry/product/parallel.rb:
#     PARALLEL_LIMIT = 50

RUN sed -i -e 's/LOW_NEEDS_LIMIT = [0-9]\+/LOW_NEEDS_LIMIT = 1000/g' \
           -e 's/HARD_NEEDS_LIMIT = [0-9]\+/HARD_NEEDS_LIMIT = 1000/g' \
               /srv/gitlab/lib/gitlab/ci/pipeline/seed/build.rb \
 && ss='s/return false unless Feature.enabled?(:ci_yaml_limit_size.*' \
  ; ss="$ss/return false/g" \
 && sed -i \
        -e 's/MAX_YAML_SIZE = 1\.megabyte\+/MAX_YAML_SIZE = 1024\.megabyte/g' \
        -e "$ss" /srv/gitlab/lib/gitlab/config/loader/yaml.rb
