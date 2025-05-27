module "delete_stale_branches_token" {
  source = "./modules/spackbot_personal_access_token"

  name   = "delete-stale-branches cronjob personal access token"
  scopes = ["api"]
}

resource "kubectl_manifest" "delete_stale_branches" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: delete-stale-branches-credentials
      namespace: custom
    data:
      gitlab-token: ${base64encode("${module.delete_stale_branches_token.token}")}
  YAML
}
