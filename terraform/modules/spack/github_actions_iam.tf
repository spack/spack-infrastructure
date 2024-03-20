locals {
  iam_role_name = "GitHubActionsReadonlyRole-${var.deployment_name}"
}

resource "aws_iam_role" "github_actions" {
  name        = local.iam_role_name
  description = "Managed by Terraform. IAM Role that a GitHub Actions runner can assume to authenticate with AWS."

  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : var.github_actions_oidc_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringLike" : {
            "token.actions.githubusercontent.com:sub" : "repo:spack/spack-infrastructure:ref:refs/heads/main",
            "token.actions.githubusercontent.com:aud" : "sts.amazonaws.com"
          }
        }
      },
      {
        "Action" : "sts:AssumeRole",
        "Principal" : {
          # Unfortunately, we need to do this until https://github.com/hashicorp/terraform-provider-aws/issues/27034 is resolved.
          # This trust statement allows the role to assume itself, which is necessary for the GitHub Actions session user to run terraform plan.
          "AWS" : "arn:aws:sts::${data.aws_caller_identity.current.account_id}:assumed-role/GitHubActionsReadonlyRole-${var.deployment_name}/GitHubActions"
        },
        "Effect" : "Allow",
      },
    ]
  })

  # The `ReadOnlyAccess` managed policy doesn't include secretsmanager, so we explicitly grant it here.
  inline_policy {
    name = "read-secrets"
    policy = jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : [
            "secretsmanager:GetSecretValue"
          ],
          "Resource" : "*"
        }
      ]
    })
  }
}

# This policy grants the GitHub Actions role read-only access to most resources in the AWS account.
# There are some exceptions, such as secretsmanager (see inline_policy above)
resource "aws_iam_role_policy_attachment" "github_actions" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# This ClusterRole and ClusterRoleBinding allow for read-only access to the
# Kubernetes cluster. This allows the GitHub Actions role to run a `terraform plan`,
# but crucially, not a `terraform apply` or other mutable actions.
resource "kubectl_manifest" "github_actions_clusterrole" {
  yaml_body = <<YAML
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRole
    metadata:
      name: github-actions-oidc
    rules:
    - apiGroups: ["*"]
      resources: ["*"]
      verbs: ["get", "list", "watch"]
  YAML
}
resource "kubectl_manifest" "github_actions_clusterrolebinding" {
  yaml_body = <<YAML
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRoleBinding
    metadata:
      name: github-actions-oidc
    subjects:
    - kind: Group
      name: github-actions
      apiGroup: rbac.authorization.k8s.io
    roleRef:
      kind: ClusterRole
      name: ${kubectl_manifest.github_actions_clusterrole.name}
      apiGroup: rbac.authorization.k8s.io
    YAML
}
