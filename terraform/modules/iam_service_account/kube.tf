resource "kubectl_manifest" "this" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: ${var.service_account_name}
      namespace: ${var.service_account_namespace}
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.this.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.this,
  ]
}
