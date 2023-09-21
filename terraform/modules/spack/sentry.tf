resource "random_password" "sentry_spackbot_password" {
  length  = 64
  lower   = true
  upper   = true
  numeric = true
  special = true
}

resource "random_password" "sentry_api_key" {
  length  = 32
  lower   = true
  upper   = true
  numeric = true
  special = false
}

resource "kubectl_manifest" "sentry_api_key_serviceaccount" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: create-sentry-api-key
      namespace: sentry
  YAML
}

resource "kubectl_manifest" "sentry_api_key_role" {
  yaml_body = <<-YAML
    kind: Role
    apiVersion: rbac.authorization.k8s.io/v1
    metadata:
      name: create-sentry-api-key
      namespace: sentry
    rules:
      - apiGroups: ["", "extensions", "apps"]
        resources: ["deployments", "pods", "pods/exec"]
        verbs: ["get", "list", "create"]
  YAML
}

resource "kubectl_manifest" "sentry_api_key_rolebinding" {
  yaml_body = <<-YAML
    kind: RoleBinding
    apiVersion: rbac.authorization.k8s.io/v1
    metadata:
      name: create-sentry-api-key
      namespace: sentry
    subjects:
      - kind: ServiceAccount
        name: ${kubectl_manifest.sentry_api_key_serviceaccount.name}
    roleRef:
      kind: Role
      name: ${kubectl_manifest.sentry_api_key_role.name}
      apiGroup: rbac.authorization.k8s.io
  YAML
}

locals {
  spackbot_email = "mike.vandenburgh+spackbot@kitware.com"
  permissions = [
    "alerts:read",
    "alerts:write",
    "event:admin",
    "event:read",
    "event:write",
    "member:admin",
    "member:read",
    "member:write",
    "org:admin",
    "org:integrations",
    "org:read",
    "org:write",
    "project:admin",
    "project:read",
    "project:releases",
    "project:write",
    "team:admin",
    "team:read",
    "team:write",
  ]
}

locals {
  api_key_scopes = "[${join(",", [
    for permission in local.permissions : "'${permission}'"
  ])}]"
}

resource "kubernetes_job" "sentry_api_key_job" {
  depends_on = [
    kubectl_manifest.sentry_api_key_rolebinding,
  ]
  metadata {
    name      = "create-sentry-api-key-job"
    namespace = "sentry"
  }
  spec {
    completions = 1
    template {
      metadata {}
      spec {
        container {
          name              = "create-sentry-api-key"
          image             = "bitnami/kubectl"
          image_pull_policy = "IfNotPresent"
          command           = ["/bin/sh", "-c"]
          args = [
            <<HEREDOC
            kubectl -n sentry exec -i deploy/sentry-web -- sentry createuser --no-input --force-update --email='${local.spackbot_email}' --password='${random_password.sentry_spackbot_password.result}' --superuser &&
            kubectl -n sentry exec -i deploy/sentry-web -- sentry shell -c "from sentry.models import ApiToken, User; ApiToken.objects.update_or_create(user=User.objects.get(username='${local.spackbot_email}'), token='${random_password.sentry_api_key.result}', defaults=dict(scopes=0, scope_list=${local.api_key_scopes}))";
            HEREDOC
          ]
        }
        restart_policy       = "OnFailure"
        service_account_name = kubectl_manifest.sentry_api_key_serviceaccount.name
        node_selector = {
          "spack.io/node-pool" = "base"
        }
      }
    }
  }
  # Setting this to true forces Terraform to wait for the API
  # key to be created before creating any sentry resources.
  wait_for_completion = true
}

data "kubernetes_ingress_v1" "sentry" {
  metadata {
    name      = "sentry"
    namespace = "sentry"
  }

  depends_on = [
    # This forces the sentry provider block to wait for the
    # API key job to finish before authenticating.
    kubernetes_job.sentry_api_key_job,
  ]
}

locals {
  sentry_domain = data.kubernetes_ingress_v1.sentry.spec[0].rule[0].host
}

provider "sentry" {
  base_url = "https://${local.sentry_domain}/api/"
  token    = random_password.sentry_api_key.result
}


data "sentry_organization" "default" {
  slug = "sentry"

  depends_on = [
    kubernetes_job.sentry_api_key_job
  ]
}

resource "sentry_team" "spack" {
  organization = data.sentry_organization.default.id

  name = "spack"
}

resource "sentry_project" "gitlab_server" {
  organization = data.sentry_organization.default.id

  teams = [sentry_team.spack.id]
  name  = "GitLab Server"
  slug  = "gitlab-server"

  platform = "ruby-rails"
}

data "sentry_key" "gitlab_server" {
  organization = data.sentry_organization.default.id
  project      = sentry_project.gitlab_server.id
}

resource "sentry_project" "gitlab_client" {
  organization = data.sentry_organization.default.id

  teams = [sentry_team.spack.id]
  name  = "GitLab Client"
  slug  = "gitlab-client"

  platform = "ruby-rails"
}

data "sentry_key" "gitlab_client" {
  organization = data.sentry_organization.default.id
  project      = sentry_project.gitlab_client.id
}

resource "kubectl_manifest" "gitlab_sentry_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-sentry-config
      namespace: gitlab
    data:
      values.yaml: |
        global:
          appConfig:
            sentry:
              enabled: true
              dsn: ${data.sentry_key.gitlab_server.dsn_public}
              clientside_dsn: ${data.sentry_key.gitlab_client.dsn_public}
              environment: ${var.deployment_name}
  YAML
}

resource "kubectl_manifest" "sentry_ses_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: sentry-ses-config
      namespace: sentry
    data:
      values.yaml: |
        mail:
          backend: smtp
          useTls: true
          username: ${aws_iam_access_key.ses_user.id}
          password: ${aws_iam_access_key.ses_user.ses_smtp_password_v4}
          port: 587
          host: email-smtp.${data.aws_region.current.name}.amazonaws.com
          from: admin@${local.sentry_domain}
  YAML
}
