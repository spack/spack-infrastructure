# AWS Infrastructure

The current infrastructure in the AWS Cloud is maintained via this git
repository.  This page will walk through the process that it would take to
replicate these parts in a new instance of a cloud infrastructure service.

The existing framework utilizes:

* [Kubernetes](https://kubernetes.io/)
    * "The open-source system for automating deployment, scaling, and management
       of containerized applications"
* [Helm](https://helm.sh/)
    * "The package manager for Kubernetes"
* [Flux](https://fluxcd.io/)
    * "Flux is a tool for keeping Kubernetes clusters in sync with sources of
      configuration (like Git repositories), and automating updates to
      configuration when there is new code to deploy."


## Recreation of SPACK infrastructure

### Set up Flux

Alter the `Git` section of the `flux-chart.yaml` file found in the
`k8s-bootstrap` directory.

Then, execute the `bootstrap.sh` file found in the `k8s-bootstrap` directory.
This file will use `kubectl` along with Helm to install the Flux "package" and
inform Flux of the location of the repository and branch that it should survey.

### Start GitOps controller

Alter  `deployments.yaml` in the `k8s/gitops` directory.  The updated values
should point to a repository.

This long running task will keep an constant watch on the repository.  It's task
is to monitor three branches of an instance of the `spack-infrastructure`
repository for changes to the content in each branch.

The first branch set by `--staging-branch` <does something different
as only some stuff goes into a staging location>

The second branch, set by `--production-branch`, indicates the "desired" state
of the Helm charts in the cluster.  When this branch is updated, via a pull
request or merge, the GitOps service will <read the files from all of the
folders and commit parsed versions of them > into a directory on the third branch
set by the `--target-branch` argument.  These `target-branch` and `target-dir`
values *need* to be the same as set in the Flux setup above.  

As work is done to the repository and changes are made to the files in the
target directory on the targeted branch, Flux will attempt to apply the
configuration of each YAML file that it finds to the running cluster.

**Note:** This could overwrite work done on the cluster, if the
manual changes were to one of the tracked objects.  Other newly created objects,
such as a new deployment, namespace, or pod will be left alone when Flux
determines that an update is necessary.


## Helm Releases for Individual parts

|        Name        | Chart Version  |  Program Version  |
| ------------------ | -------------- | ----------------- |
| Gitlab Runner      |    0.37.2      |      14.7.0       |
| Gitlab             |    5.6.3       |      14.6.3       |
| cluster-autoscaler |    9.9.2       |      1.20.0       |
| ingress-nginx      |    3.4.0       |      0.40.1       |
