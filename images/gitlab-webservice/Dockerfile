FROM registry.gitlab.com/gitlab-org/build/cng/gitlab-webservice-ee:v14.6.3

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

RUN ss='s/return false unless Feature.enabled?(:ci_yaml_limit_size.*' \
  ; ss="$ss/return false/g" \
 && sed -i \
        -e 's/MAX_YAML_SIZE = 1\.megabyte\+/MAX_YAML_SIZE = 1024\.megabyte/g' \
        -e "$ss" /srv/gitlab/lib/gitlab/config/loader/yaml.rb
