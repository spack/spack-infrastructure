resource "aws_iam_role" "aws_load_balancer_controller" {
  name        = "aws-load-balancer-controller-role-${var.deployment_name}-${var.deployment_stage}"
  description = "Managed by Terraform. IAM role for AWS Load Balancer Controller to manage ALBs/NLBs"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com",
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:aws-load-balancer-controller:aws-load-balancer-controller"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "aws_load_balancer_controller" {
  name = "aws-load-balancer-controller-policy-${var.deployment_name}-${var.deployment_stage}"
  # Official recommended IAM policy from:
  # https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/191587d6df464cf6b17a984b0942a359724f31f3/docs/install/iam_policy.json
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "iam:CreateServiceLinkedRole"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringEquals" : {
            "iam:AWSServiceName" : "elasticloadbalancing.amazonaws.com"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DescribeAccountAttributes",
          "ec2:DescribeAddresses",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeVpcs",
          "ec2:DescribeVpcPeeringConnections",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeInstances",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeTags",
          "ec2:GetCoipPoolUsage",
          "ec2:DescribeCoipPools",
          "ec2:GetSecurityGroupsForVpc",
          "ec2:DescribeIpamPools",
          "ec2:DescribeRouteTables",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeLoadBalancerAttributes",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeListenerCertificates",
          "elasticloadbalancing:DescribeSSLPolicies",
          "elasticloadbalancing:DescribeRules",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetGroupAttributes",
          "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:DescribeTags",
          "elasticloadbalancing:DescribeTrustStores",
          "elasticloadbalancing:DescribeListenerAttributes",
          "elasticloadbalancing:DescribeCapacityReservation"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "cognito-idp:DescribeUserPoolClient",
          "acm:ListCertificates",
          "acm:DescribeCertificate",
          "iam:ListServerCertificates",
          "iam:GetServerCertificate",
          "waf-regional:GetWebACL",
          "waf-regional:GetWebACLForResource",
          "waf-regional:AssociateWebACL",
          "waf-regional:DisassociateWebACL",
          "wafv2:GetWebACL",
          "wafv2:GetWebACLForResource",
          "wafv2:AssociateWebACL",
          "wafv2:DisassociateWebACL",
          "shield:GetSubscriptionState",
          "shield:DescribeProtection",
          "shield:CreateProtection",
          "shield:DeleteProtection"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:RevokeSecurityGroupIngress"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateSecurityGroup"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateTags"
        ],
        "Resource" : "arn:aws:ec2:*:*:security-group/*",
        "Condition" : {
          "StringEquals" : {
            "ec2:CreateAction" : "CreateSecurityGroup"
          },
          "Null" : {
            "aws:RequestTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateTags",
          "ec2:DeleteTags"
        ],
        "Resource" : "arn:aws:ec2:*:*:security-group/*",
        "Condition" : {
          "Null" : {
            "aws:RequestTag/elbv2.k8s.aws/cluster" : "true",
            "aws:ResourceTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:RevokeSecurityGroupIngress",
          "ec2:DeleteSecurityGroup"
        ],
        "Resource" : "*",
        "Condition" : {
          "Null" : {
            "aws:ResourceTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:CreateLoadBalancer",
          "elasticloadbalancing:CreateTargetGroup"
        ],
        "Resource" : "*",
        "Condition" : {
          "Null" : {
            "aws:RequestTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:CreateListener",
          "elasticloadbalancing:DeleteListener",
          "elasticloadbalancing:CreateRule",
          "elasticloadbalancing:DeleteRule"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:AddTags",
          "elasticloadbalancing:RemoveTags"
        ],
        "Resource" : [
          "arn:aws:elasticloadbalancing:*:*:targetgroup/*/*",
          "arn:aws:elasticloadbalancing:*:*:loadbalancer/net/*/*",
          "arn:aws:elasticloadbalancing:*:*:loadbalancer/app/*/*"
        ],
        "Condition" : {
          "Null" : {
            "aws:RequestTag/elbv2.k8s.aws/cluster" : "true",
            "aws:ResourceTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:AddTags",
          "elasticloadbalancing:RemoveTags"
        ],
        "Resource" : [
          "arn:aws:elasticloadbalancing:*:*:listener/net/*/*/*",
          "arn:aws:elasticloadbalancing:*:*:listener/app/*/*/*",
          "arn:aws:elasticloadbalancing:*:*:listener-rule/net/*/*/*",
          "arn:aws:elasticloadbalancing:*:*:listener-rule/app/*/*/*"
        ]
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:ModifyLoadBalancerAttributes",
          "elasticloadbalancing:SetIpAddressType",
          "elasticloadbalancing:SetSecurityGroups",
          "elasticloadbalancing:SetSubnets",
          "elasticloadbalancing:DeleteLoadBalancer",
          "elasticloadbalancing:ModifyTargetGroup",
          "elasticloadbalancing:ModifyTargetGroupAttributes",
          "elasticloadbalancing:DeleteTargetGroup",
          "elasticloadbalancing:ModifyListenerAttributes",
          "elasticloadbalancing:ModifyCapacityReservation",
          "elasticloadbalancing:ModifyIpPools"
        ],
        "Resource" : "*",
        "Condition" : {
          "Null" : {
            "aws:ResourceTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:AddTags"
        ],
        "Resource" : [
          "arn:aws:elasticloadbalancing:*:*:targetgroup/*/*",
          "arn:aws:elasticloadbalancing:*:*:loadbalancer/net/*/*",
          "arn:aws:elasticloadbalancing:*:*:loadbalancer/app/*/*"
        ],
        "Condition" : {
          "StringEquals" : {
            "elasticloadbalancing:CreateAction" : [
              "CreateTargetGroup",
              "CreateLoadBalancer"
            ]
          },
          "Null" : {
            "aws:RequestTag/elbv2.k8s.aws/cluster" : "false"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:RegisterTargets",
          "elasticloadbalancing:DeregisterTargets"
        ],
        "Resource" : "arn:aws:elasticloadbalancing:*:*:targetgroup/*/*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "elasticloadbalancing:SetWebAcl",
          "elasticloadbalancing:ModifyListener",
          "elasticloadbalancing:AddListenerCertificates",
          "elasticloadbalancing:RemoveListenerCertificates",
          "elasticloadbalancing:ModifyRule",
          "elasticloadbalancing:SetRulePriorities"
        ],
        "Resource" : "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "aws_load_balancer_controller" {
  role       = aws_iam_role.aws_load_balancer_controller.name
  policy_arn = aws_iam_policy.aws_load_balancer_controller.arn
}

# TODO: apply "CriticalAddonsOnly" toleration so that it can run on the
# `bootstrap-node-group` managed node group
resource "helm_release" "aws_load_balancer_controller" {
  name             = "aws-load-balancer-controller"
  namespace        = "aws-load-balancer-controller"
  create_namespace = true

  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = "3.0.0"

  values = [
    <<-EOT
    clusterName: ${module.eks.cluster_name}
    vpcId: ${module.vpc.vpc_id}
    serviceAccount:
      name: aws-load-balancer-controller
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.aws_load_balancer_controller.arn}
    nodeSelector:
      spack.io/node-pool: beefy
    resources:
      limits:
        cpu: 500m
        memory: 512Mi
      requests:
        cpu: 100m
        memory: 128Mi
    enableCertManager: true
    podDisruptionBudget:
      maxUnavailable: 1
    createIngressClassResource: false  # We're using Gateway API, not Ingress
    defaultTargetType: ip  # Needed, because our Service type is ClusterIP
    controllerConfig:
      featureGates:
        ALBGatewayAPI: true  # Enables the Gateway API controller, it's not enabled by default
    EOT
  ]

  depends_on = [aws_iam_role_policy_attachment.aws_load_balancer_controller]
}

# --- ACM Certificate for ALB TLS termination ---

resource "aws_acm_certificate" "gateway" {
  domain_name               = "${local.domain_suffix}spack.io"
  subject_alternative_names = ["*.${local.domain_suffix}spack.io"]
  validation_method         = "DNS"
}

resource "aws_route53_record" "gateway_acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.gateway.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 300
  type            = each.value.type
  zone_id         = data.aws_route53_zone.spack_io.zone_id
}

resource "aws_acm_certificate_validation" "gateway" {
  certificate_arn         = aws_acm_certificate.gateway.arn
  validation_record_fqdns = [for record in aws_route53_record.gateway_acm_validation : record.fqdn]
}

# --- Gateway API CRDs ---
# Fetched and applied by Terraform so the Kubernetes provider tracks state and manages lifecycle.

data "http" "gateway_api_crds" {
  url = "https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml"

  request_headers = {
    Accept = "application/yaml"
  }
}
resource "kubectl_manifest" "gateway_api_crds" {
  yaml_body = data.http.gateway_api_crds.response_body
}

data "http" "aws_lbc_gateway_crds" {
  url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/refs/heads/main/helm/aws-load-balancer-controller/crds/gateway-crds.yaml"

  request_headers = {
    Accept = "application/yaml"
  }
}
resource "kubectl_manifest" "aws_lbc_gateway_crds" {
  yaml_body  = data.http.aws_lbc_gateway_crds.response_body
  depends_on = [kubectl_manifest.gateway_api_crds]
}

# --- Gateway API resources ---

resource "kubectl_manifest" "gateway_api_namespace" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Namespace
    metadata:
      name: gateway-api
  YAML
}

resource "kubectl_manifest" "gateway_class" {
  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: GatewayClass
    metadata:
      name: aws-alb
    spec:
      controllerName: gateway.k8s.aws/alb
  YAML

  depends_on = [
    kubectl_manifest.gateway_api_crds,
    helm_release.aws_load_balancer_controller,
  ]
}

resource "kubectl_manifest" "gateway_lb_config" {
  yaml_body = <<-YAML
    apiVersion: gateway.k8s.aws/v1beta1
    kind: LoadBalancerConfiguration
    metadata:
      name: spack-alb-config
      namespace: gateway-api
    spec:
      scheme: internet-facing
      loadBalancerAttributes:
        - key: idle_timeout.timeout_seconds
          value: "3600"
        - key: routing.http2.enabled
          value: "true"
        - key: access_logs.s3.enabled
          value: "false"
      listenerConfigurations:
        - protocolPort: HTTPS:443
          defaultCertificate: ${aws_acm_certificate.gateway.arn}
          sslPolicy: ELBSecurityPolicy-TLS-1-2-2017-01
      tags:
        Environment: ${var.deployment_name}
        ManagedBy: aws-load-balancer-controller
        Application: spack
  YAML

  depends_on = [
    kubectl_manifest.aws_lbc_gateway_crds,
    kubectl_manifest.gateway_api_namespace,
    aws_acm_certificate_validation.gateway,
  ]
}

resource "kubectl_manifest" "gateway" {
  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: spack-gateway
      namespace: gateway-api
    spec:
      gatewayClassName: aws-alb
      infrastructure:
        parametersRef:
          kind: LoadBalancerConfiguration
          name: spack-alb-config
          group: gateway.k8s.aws
      listeners:
        - name: http
          protocol: HTTP
          port: 80
          allowedRoutes:
            namespaces:
              from: All
        - name: https
          protocol: HTTPS
          port: 443
          allowedRoutes:
            namespaces:
              from: All
  YAML

  depends_on = [
    kubectl_manifest.gateway_api_crds,
    kubectl_manifest.gateway_api_namespace,
    kubectl_manifest.gateway_class,
    kubectl_manifest.gateway_lb_config,
  ]
}

# --- DNS: wildcard record pointing to the ALB ---

# Look up the ALB created by the LBC controller.
# NOTE: The ALB is created asynchronously by the LBC after the Gateway resource
# is applied. If this data source fails on the first `terraform apply`, re-run
# it after the ALB has been created.
data "aws_lb" "gateway" {
  tags = {
    "elbv2.k8s.aws/cluster" = module.eks.cluster_name
    "Application"           = "spack"
  }

  depends_on = [kubectl_manifest.gateway]
}

resource "aws_route53_record" "gateway_wildcard" {
  zone_id = data.aws_route53_zone.spack_io.zone_id
  name    = "*.${local.domain_suffix}spack.io"
  type    = "A"

  alias {
    name                   = data.aws_lb.gateway.dns_name
    zone_id                = data.aws_lb.gateway.zone_id
    evaluate_target_health = true
  }
}
