locals {
  github_domain = "token.actions.githubusercontent.com"

  mirror_roles = {
    "sts.amazonaws.com" = {
      "role_name_suffix"     = "SpackSourceMirror${var.deployment_name == "prod" ? "" : "-${var.deployment_name}"}-${var.deployment_stage}",
      "conditions" = [
        "repo:spack/spack-packages:ref:refs/heads/develop",
      ],
    },
  }
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "github_oidc_assume_role" {
  for_each = local.mirror_roles

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.github_domain}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_domain}:aud"
      values   = [each.key]
    }

    condition {
      test     = "StringEqual"
      variable = "${local.github_domain}:sub"
      values   = each.value.conditions
    }
  }
}

resource "aws_iam_role" "source_mirror_sync" {
  for_each = data.aws_iam_policy_document.github_oidc_assume_role

  name                 = "SourceMirrorSync${local.mirror_roles[each.key].role_name_suffix}"
  assume_role_policy   = each.value.json
  max_session_duration = 3600 * 1 # only allow a max of 1 hours for a session to be active
}
