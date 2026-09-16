# DNS for ssh.gitlab[.<deployment>].spack.io, the host GitLab advertises in SSH
# clone URLs (global.hosts.ssh in k8s/*/gitlab/). The gitlab chart creates
# gitlab-shell as a type: LoadBalancer Service but no DNS for it. The wildcard
# record in spack_aws_k8s points at the gateway ALB, which only listens on 80/443,
# so SSH needs its own record pointing at the gitlab-shell load balancer.

# NOTE: On a fresh deployment this fails until Flux has installed the GitLab
# chart and the Service has been assigned a load balancer. Re-run the apply once
# it has, the same as the gateway ALB lookup in spack_aws_k8s.
data "kubernetes_service" "gitlab_shell" {
  metadata {
    # <helm release>-gitlab-shell, and the HelmRelease is named "gitlab".
    name      = "gitlab-gitlab-shell"
    namespace = "gitlab"
  }
}

resource "aws_route53_record" "gitlab_ssh" {
  zone_id = data.aws_route53_zone.spack_io.zone_id
  name    = local.gitlab_ssh_host
  type    = "CNAME"
  ttl     = 300

  records = [
    data.kubernetes_service.gitlab_shell.status[0].load_balancer[0].ingress[0].hostname
  ]

  # Adopts the pre-existing hand-created record at this name, which both
  # deployments have, instead of failing on the first apply.
  allow_overwrite = true
}
