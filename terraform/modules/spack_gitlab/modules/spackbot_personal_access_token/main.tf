locals {
  # GitLab no longer allows tokens to be created with an indefinite expiration date,
  # so we set a long expiration date and a warning date to remind us to update it.
  token_expiration_date = "2026-04-25"
}

locals {
  # Set the token expiration warning date to one month before the expiration date
  # so that `terraform apply` will start failing a month before the expiration date.
  # This should give us plenty of time to notice and update the token before it actually expires.

  # Note: the largest time unit terraform's timeadd function supports is hours.
  token_expiration_warning_date = timeadd("${local.token_expiration_date}T00:00:00Z", "-730h")
}

resource "gitlab_personal_access_token" "this" {
  user_id    = data.gitlab_user.this.id
  name       = var.name
  expires_at = local.token_expiration_date

  scopes = var.scopes

  lifecycle {
    precondition {
      condition     = timecmp(timestamp(), local.token_expiration_warning_date) == -1
      error_message = "The ${var.name} GitLab PAT will expire in less than a month. Update the expiration date as soon as possible."
    }
  }
}

data "gitlab_user" "this" {
  username = "spackbot"
}
