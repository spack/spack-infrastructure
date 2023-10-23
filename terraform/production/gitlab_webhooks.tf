# TODO: move these resources into the `spack` module when staging can support them as well.

data "gitlab_project" "spack" {
  path_with_namespace = "spack/spack"
}

resource "gitlab_project_hook" "error_processor" {
  project                 = data.gitlab_project.spack.id
  url                     = "http://gitlab-error-processor.custom.svc.cluster.local"
  job_events              = true
  push_events             = false
  enable_ssl_verification = false
}

resource "gitlab_project_hook" "build_time_processor" {
  project                 = data.gitlab_project.spack.id
  url                     = "http://build-timing-processor.custom.svc.cluster.local"
  job_events              = true
  push_events             = false
  enable_ssl_verification = false
}

# A GitLab Project Hook can be imported using a key composed of `<project-id>:<hook-id>`
# https://registry.terraform.io/providers/gitlabhq/gitlab/latest/docs/resources/project_hook#import
import {
  to = gitlab_project_hook.error_processor
  id = "2:3"
}
import {
  to = gitlab_project_hook.build_time_processor
  id = "2:5"
}
