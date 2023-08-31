resource "gitlab_group" "spack" {
  name             = "spack"
  path             = "spack"
  description      = ""
  visibility_level = "public"
}

resource "gitlab_project" "spack" {
  name         = "spack"
  namespace_id = gitlab_group.spack.id

  visibility_level       = "public"
  default_branch = "develop"
}

resource "gitlab_branch" "spack" {
  name    = "develop"
  ref     = "main"
  project = gitlab_project.spack.id
}

resource "gitlab_repository_file" "spack" {
  project        = gitlab_project.spack.id
  file_path      = "test.txt"
  branch         = "develop"
  content        = "test"
  author_email   = "spackbot@spack.io"
  author_name    = "spackbot"
  commit_message = "test"
}

resource "random_password" "spack" {
  length  = 32
  special = true
}

resource "gitlab_user" "spack" {
  name     = "Spack Bot"
  username = "spackbot"
  password = random_password.spack.result
  email    = "mike.vandenburgh@kitware.com"
  is_admin = true
}

resource "tls_private_key" "spack" {
  algorithm = "ED25519"
}

resource "gitlab_user_sshkey" "spack" {
  user_id = gitlab_user.spack.id
  title   = "spackbot-ssh-key"
  key     = tls_private_key.spack.public_key_openssh
}

resource "kubectl_manifest" "gh_gl_sync_secrets" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
        name: gh-gl-sync
        namespace: custom
    annotations:
        kustomize.toolkit.fluxcd.io/reconcile: disabled
    data:
        github-access-token: ${base64encode("test")}
        gitlab-ssh-key: ${base64encode("${base64encode("${tls_private_key.spack.private_key_openssh}")}")}
  YAML
}
