locals {
  job_webhooks = ["http://gitlab-error-processor.custom.svc.cluster.local",
  "http://build-timing-processor.custom.svc.cluster.local"]
}


resource "gitlab_project_hook" "job_webhook" {
  for_each = toset(local.job_webhooks)

  project                 = data.gitlab_project.spack.id
  url                     = each.value
  job_events              = true
  push_events             = false
  enable_ssl_verification = false
}

// TODO: Once https://gitlab.com/gitlab-org/terraform-provider-gitlab/-/issues/1350 is resolved the
// gitlab_application_settings resource should be used to whitelist the domains in job_webhooks.
