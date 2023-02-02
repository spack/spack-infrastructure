locals {
  known_hosts = "github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg="
  install = [for v in data.kubectl_file_documents.install.documents : {
    data : yamldecode(v)
    content : v
    }
  ]
  sync = [for v in data.kubectl_file_documents.sync.documents : {
    data : yamldecode(v)
    content : v
    }
  ]
}

resource "tls_private_key" "main" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

data "flux_install" "main" {
  target_path = var.flux_target_path
}

data "flux_sync" "main" {
  target_path = var.flux_target_path
  url         = "https://github.com/${var.flux_repo_owner}/${var.flux_repo_name}"
  branch      = var.flux_branch
}

resource "kubectl_manifest" "flux_system_namespace" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Namespace
    metadata:
        name: flux-system
  YAML
}

data "kubectl_file_documents" "install" {
  content = data.flux_install.main.content
}

data "kubectl_file_documents" "sync" {
  content = data.flux_sync.main.content
}

resource "kubectl_manifest" "install" {
  for_each   = { for v in local.install : lower(join("/", compact([v.data.apiVersion, v.data.kind, lookup(v.data.metadata, "namespace", ""), v.data.metadata.name]))) => v.content }
  depends_on = [kubectl_manifest.flux_system_namespace]
  yaml_body  = each.value
}

resource "kubectl_manifest" "sync" {
  for_each   = { for v in local.sync : lower(join("/", compact([v.data.apiVersion, v.data.kind, lookup(v.data.metadata, "namespace", ""), v.data.metadata.name]))) => v.content }
  depends_on = [kubectl_manifest.flux_system_namespace]
  yaml_body  = each.value
}

resource "kubectl_manifest" "flux_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
        name: ${data.flux_sync.main.secret}
        namespace: ${data.flux_sync.main.namespace}
    annotations:
        kustomize.toolkit.fluxcd.io/reconcile: disabled
    data:
        identity: ${base64encode("${tls_private_key.main.private_key_pem}")}
        identity.pub: ${base64encode("${tls_private_key.main.public_key_pem}")}
        known_hosts: ${base64encode("${local.known_hosts}")}
  YAML
}

resource "github_branch_default" "main" {
  repository = var.flux_repo_name
  branch     = var.flux_branch
}

resource "github_repository_file" "install" {
  repository          = var.flux_repo_name
  file                = data.flux_install.main.path
  content             = data.flux_install.main.content
  branch              = var.flux_branch
  overwrite_on_create = true
}

resource "github_repository_file" "sync" {
  repository          = var.flux_repo_name
  file                = data.flux_sync.main.path
  content             = data.flux_sync.main.content
  branch              = var.flux_branch
  overwrite_on_create = true
}

resource "github_repository_file" "kustomize" {
  repository          = var.flux_repo_name
  file                = data.flux_sync.main.kustomize_path
  content             = data.flux_sync.main.kustomize_content
  branch              = var.flux_branch
  overwrite_on_create = true
}
