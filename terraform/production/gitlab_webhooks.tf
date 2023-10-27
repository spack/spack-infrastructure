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
