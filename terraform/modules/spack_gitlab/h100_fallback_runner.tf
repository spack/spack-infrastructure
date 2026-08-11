# H100 EC2 fallback runner for illyad (see k8s/production/runners/public/h100-fallback/).
# Registered in both prod and staging - staging validates the whole chain
# (NodePool provisioning, GPU scheduling, runner registration).

resource "gitlab_user_runner" "h100_fallback" {
  runner_type = "instance_type"
  description = "Managed by Terraform. H100 EC2 fallback runner."
  tag_list    = ["hpsf-gpu", "nvidia-h100", "x86_64-nvidiagpu"]
  untagged    = false
  locked      = false
}

# The gitlab-runner chart's projected volume unconditionally requires both
# keys below to exist on the referenced Secret (see
# k8s/production/runners/public/h100-fallback/release.yaml), even though
# only runner-token is used by this runner-token-based registration flow -
# runner-registration-token is sealed as an empty string to satisfy that.
resource "kubectl_manifest" "h100_fallback_runner_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: spack-instance-runner-secret
      namespace: gitlab
    data:
      runner-registration-token: "${base64encode("")}"
      runner-token: ${base64encode(gitlab_user_runner.h100_fallback.token)}
  YAML
}
