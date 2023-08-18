# locals {
#   hostname   = "sentry.staging.spack.io"
#   tls_secret_name = "tls-sentry"
# }

# resource "kubectl_manifest" "sentry_namespace" {
#   yaml_body = <<-YAML
#     apiVersion: v1
#     kind: Namespace
#     metadata:
#       name: sentry
#   YAML
# }

# resource "kubectl_manifest" "sentry_certificates" {
#   yaml_body = <<-YAML
#     apiVersion: cert-manager.io/v1
#     kind: Certificate
#     metadata:
#       name: sentry
#       namespace: ${kubectl_manifest.sentry_namespace.name}
#     spec:
#       secretName: ${local.tls_secret_name}
#       issuerRef:
#         name: letsencrypt
#         kind: ClusterIssuer
#       dnsNames:
#         - ${local.hostname}
#   YAML
# }


# # resource "helm_release" "sentry" {
# #   namespace        = kubectl_manifest.sentry_namespace.name
# #   create_namespace = false  # this is created below in its own resource
# #   # timeout          = 60 * 20

# #   name       = "sentry"
# #   repository = "https://sentry-kubernetes.github.io/charts"
# #   chart      = "sentry"
# #   version    = "20.0.0"

# #   set {
# #     name = "hooks.activeDeadlineSeconds"
# #     value = 1000
# #   }

# #   set {
# #     name  = "ingress.enabled"
# #     value = true
# #   }

# #   set {
# #     name  = "ingress.annotations.kubernetes\\.io/ingress\\.class"
# #     value = "nginx"
# #   }

# #   set {
# #     name  = "ingress.hostname"
# #     value = local.hostname
# #   }

# #   set {
# #     name  = "ingress.tls[0].secretName"
# #     value = local.tls_secret_name
# #   }

# #   set {
# #     name  = "ingress.tls[0].hosts[0]"
# #     value = local.hostname
# #   }

# #   depends_on = [kubectl_manifest.sentry_certificates]
# # }
