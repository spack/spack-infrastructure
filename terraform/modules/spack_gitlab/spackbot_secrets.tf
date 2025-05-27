module "spackbot_token" {
  source = "./modules/spackbot_personal_access_token"

  name   = "spackbot personal access token"
  scopes = ["api"]
}

resource "kubectl_manifest" "spackbot_gitlab_credentials" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: spack-bot-gitlab-credentials
      namespace: spack
    data:
      gitlab_token: ${base64encode("${module.spackbot_token.token}")}
  YAML
}
