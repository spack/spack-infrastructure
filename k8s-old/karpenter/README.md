# Setting up Karpenter

This will detail the steps necessary to get karpenter running on an existing EKS cluster. The following assumptions are made:

* There is an existing EKS cluster
* There is existing VPC and subnets for nodes (or ASGs)
* There is an existing security group for nodes (or ASGs)
* The cluster has an OIDC provider for service accounts


## Getting Started

Follow [this](https://karpenter.sh/v0.17.0/getting-started/migrating-from-cas/) guide, modifying the following steps:

## Add tags to subnets and security groups

At this step, the guide might not match your cluster / infrastructure. What matters is that you add the `karpenter.sh/discovery=spack` tag to whatever subnets and security groups will be used. For the current spack EKS cluster, this equates to 4 subnets (one for each us-east-1 availability zone), and one security group.


**Note:** Be sure to tag a subnet in each availability zone that you intend for nodes to be available in. If you forget to tag a subnet, that availability zone can't be used to scale up nodes, even if that zone is included in your karpenter provisioner. This can be a particular issue for spot instance availability.


## Set node affinity
In my experience this step wasn't necessary

## Remove CAS
This may or may not be the correct way to handle turning off cluster autoscaler for your use case.


# Adding / Modifying provisioners
The above guide only creates a default provisioner, however you'll likely need to add some constraints/requirements like:
* Availability zones
* Allowed architecture
* Allowed instance types
* Spot vs on-demand nodes
* Resource limits

Here are some resources
* [AWS provisoning docs](https://karpenter.sh/v0.17.0/aws/provisioning/)
* [Provisioner API docs](https://karpenter.sh/v0.17.0/provisioner/)


# Applying this configuration

To deploy Karpenter onto the cluster, simply run (from this directory)
```
kubectl apply -f karpenter/
```

To apply the defined provisioners, node templates, etc. simply run (from this directory)
```
kubectl apply -f .
```
