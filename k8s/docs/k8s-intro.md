### Introduction to Kubernetes: Deploying a simple, stateless service.

This tutorial assumes that you have a simple containerized application that runs
a service that (beyond what is in the container) has no state.  This tutorial
serves as a basic Kubernetes introduction aimed at deploying such a service.

#### 0 - Kubernetes Design Concepts

Kubernetes manages infrastructure using the [controller
pattern](https://kubernetes.io/docs/concepts/architecture/controller), a process
inspired from robotics and automation.  In Kubernetes, administrators and users
declaratively communicate *desired* state, and the system is implicitly
understood to eventually assume this state at some later time.  Within a
Kubernetes system, various pieces of monitoring software continuously run tight
loops where this desired state is compared against the current state and actions
are taken in response to any detected differences.  These actions are taken with
the intent of iteratively transitioning the current state towards the desired
state.  It is through this combination of continuous monitoring, differential
analysis, and automatic inducing of transitions that a Kubernetes system's state
is controlled.  The tight loops that automate this control are called "control
loops" and the pieces of software that run these loops are called "controllers".

Kubernetes also introduces a data model for system state based on strict
versioning, which minimizes tight coupling between controllers and allows
development and operation of these controllers and their constituent states to
proceed independently of each other.  At its core, the Kubernetes data model
consists almost entirely of "types" of state data (or "kind"s of state) and
various controllers designed to respond to changes to instances of these kinds
of state.  A controller's actions often have side effects that introduce
changes to other, related kinds of state, and which often elicit responses from
other controllers in turn.  Thus, while the action of any one controller is
relatively simple to understand, their collective operation routinely involves
large, cascading chain-reactions from whose aggregate effects emerge
infrastructure automation of considerable sophistication.

The next sections will discuss some of the state kinds that are common
throughout most Kubernetes systems and the typical operations of their
respective controllers.

#### 1 - Pods

Pods encapsulate a collection of containers into a single logical service unit.
The containers that make up a pod share a networking namespace and a set of
volume mounts, among other things.  Pods serve as the foundational atomic unit
of computation, upon which all higher-level workload kinds are built and around
which all higher-level orchestration mechanisms are centered.

The `kubectl` client can be used to query the server for documentation about
Pods, or any other kind understood by the server:

```console
 $ kubectl explain pods
```
```console
KIND:     Pod
VERSION:  v1

DESCRIPTION:
     Pod is a collection of containers that can run on a host. This resource is
     created by clients and scheduled onto hosts.

FIELDS:
   apiVersion   <string>
     APIVersion defines the versioned schema of this representation of an
     object. Servers should convert recognized schemas to the latest internal
     value, and may reject unrecognized values. More info:
     https://git.k8s.io/community/contributors/devel/sig-architecture/api-con...

   kind <string>
     Kind is a string value representing the REST resource this object
     represents. Servers may infer this from the endpoint the client submits
     requests to. Cannot be updated. In CamelCase. More info:
     https://git.k8s.io/community/contributors/devel/sig-architecture/api-con...

   metadata     <Object>
     Standard object's metadata. More info:
     https://git.k8s.io/community/contributors/devel/sig-architecture/api-con...

   spec <Object>
     Specification of the desired behavior of the pod. More info:
     https://git.k8s.io/community/contributors/devel/sig-architecture/api-con...

   status       <Object>
     Most recently observed status of the pod. This data may not be up to date.
     Populated by the system. Read-only. More info:
     https://git.k8s.io/community/contributors/devel/sig-architecture/api-con...
```

This output shows multiple features that are common among all Kubernetes kinds.
Every state kind has an `apiVersion` that dictates the schema that the server
will expect for this state, a `kind` field specifying the state kind, `metadata`
specifying various pieces of metadata, and a `spec`, which provides the
specification for the state, proper.

For this tutorial, we will prepare and present our desired state in the form of
YAML files.  We begin by preparing a simple YAML file for a single Pod:

```YAML
---
apiVersion: v1
kind: Pod
metadata:
  ...
spec:
  ...
```

We can learn more about the `metadata` schema using the same `kubectl` command:

```console
 $ kubectl explain pods.metadata
```
```console
KIND:     Pod
VERSION:  v1

RESOURCE: metadata <Object>

DESCRIPTION:
     Standard object's metadata. More info:
     https://git.k8s.io/community/contributors/devel/sig-architecture/api-con...

     ObjectMeta is metadata that all persisted resources must have, which
     includes all objects users must create.

FIELDS:
   annotations  <map[string]string>
     Annotations is an unstructured key value map stored with a resource that
     may be set by external tools to store and retrieve arbitrary metadata. They
     are not queryable and should be preserved when modifying objects. More
     info: http://kubernetes.io/docs/user-guide/annotations

   clusterName  <string>
     The name of the cluster which the object belongs to. This is used to
     distinguish resources with same name and namespace in different clusters.
     This field is not set anywhere right now and apiserver is going to ignore
     it if set in create or update request.

   creationTimestamp    <string>
     CreationTimestamp is a timestamp representing the server time when this
     object was created. It is not guaranteed to be set in happens-before order
     across separate operations. Clients may not set this value. It is
     represented in RFC3339 form and is in UTC.
...
```

We briefly detail a few of these fields:

  - `name` specifies the name of the resource (the name of the `Pod`, in this
    case).  Outside of a few exceptions, it is a required field.

  - `namespace` provides the name of a namespace for the resource.  Namespaces
     are logical groupings of related resources.  Resources in Kubernetes are
     uniquely identified by the combination of their `kind`s, `name`s, and
     `namespace`s.  In this tutorial, we don't specify a namespace, and instead
     use the `default` namespace.

  - `labels` is a set of arbitrary key-value pairs.  They are mostly intended
    for users to use as an organization aid.  Labels are often simple and can
    denote resource features, such as the name and version of the application
    the resource serves, the component thereof, or whether it is part of an
    installation meant for production or testing.

  - `annotations` is a set of arbitrary key-value pairs, just like `labels`, but
    they are typically meant to mark resources and usually to customize the
    precise manner by which those resources are managed by controllers.  As a
    convention, custom annotations are usually prefixed with the domain name for
    the organization that introduced them and may include an optional subdomain
    to denote API versioning information.  As a general rule of thumb, `labels`
    are usually informational and `annotations` are usually functional, although
    this distinction is not a hard-and-fast rule.

```
---
apiVersion: v1
kind: Pod
metadata:
  name: my-demo-pod
  namespace: default  # can be left out for "default" namespace
  annotations:
    spack.io/annotation-1: "1"
    spack.io/annotation-2: "2"
    spack.io/annotation-3: "3"
  labels:
    app: my-demo
    svc: web
    component: some-demo-pod
    other-label-1: "1"
    other-label-2: "2"
    other-label-3: "3"
spec:
  ...
```

Through successive use of the `kubectl explain` command, we can learn what
information we need to fill out the specification for the Pod, proper.  Here's
an example of how one might fill it out:

##### my-demo-pod.yaml
```
---
apiVersion: v1
kind: Pod
metadata:
  name: my-demo-pod
  namespace: default  # can be left out for "default" namespace
  annotations:
    spack.io/annotation-1: "1"
    spack.io/annotation-2: "2"
    spack.io/annotation-3: "3"
  labels:
    app: my-demo
    svc: web
    component: some-demo-pod
    other-label-1: "1"
    other-label-2: "2"
    other-label-3: "3"
spec:
  # Should Kubernetes restart a POD's containers?
  restartPolicy: Always  # default

  # Insist that this Pod runs on one of our "base" nodes.
  # (Only works on AWS)
  nodeSelector:
    spack.io/node-pool: "base"

  # list of containers to run in the Pod.
  # As is the case in this example, there's usually only one container in a Pod.
  containers:
    - name: my-demo-pod-container
      image: ghcr.io/spack/my-demo-image:v1.2.3

      # Don't (re)pull the image if it's already present in the host's cache.
      # default for tags that do *not* end in ":latest"
      imagePullPolicy: IfNotPresent

      # run this command
      # default: the image's ENTRYPOINT
      command: ["/usr/bin/...", "run-webserver"]

      # specify these additional arguments
      # default: the image's CMD
      args: ["arg-0", "arg-1", "arg-2", ...]

      # We enumerate the ports that we want kubernetes to know about.
      # Not specifying a port will *not* prevent it from being published;
      # this part is just to give kubernetes the information it needs to
      # route traffic to the Pod.
      ports:
        - name: http
          containerPort: 8080
          protocol: TCP

      # Specify any extra environment variables.
      env:
        - name: MY_ENVIRONMENT_VARIABLE_1
          value: VALUE_1
        - name: MY_ENVIRONMENT_VARIABLE_2
          value: VALUE_2
        - name: MY_ENVIRONMENT_VARIABLE_3
          value: VALUE_3
```

If we saved the above contents into a file, we could submit it to the server
using `kubectl`:

```console
 $ kubectl apply -f my-demo-pod.yaml
```
```console
pod/my-demo-pod created
```

... and we can monitor the Pod's status:

```console
 $ kubectl get pods
```
```console
NAME          READY   STATUS         RESTARTS   AGE
my-demo-pod   0/1     Pending        0          5s
```
```console
 $ kubectl get pods
```
```console
NAME          READY   STATUS              RESTARTS   AGE
my-demo-pod   0/1     ContainerCreating   0          6s
```
```console
 $ kubectl get pods
```
```console
NAME          READY   STATUS    RESTARTS   AGE
my-demo-pod   1/1     Running   0          21s
```

If the Pod referenced in the file does not already exist, Kubernetes will create
a new `Pod` resource state to represent it, and the controllers running on the
server will respond to the new state by scheduling the Pod for execution on one
of the cluster's hosts.  For resources that already exist, differences between
its existing state and the contents of the submitted `yaml` file are recorded,
and the server's controllers would respond in any number of ways depending on
the differences.  In the case of Pods, the server enforces immutability
constraints on most of a Pod's fields, so outside of a few corner-cases, a new
replacement Pod would need to be created, scheduled, and executed; and the
original Pod terminated and removed from the cluster.

```console
 $ kubectl delete pods my-demo-pod
```
```console
pod "my-demo-pod" deleted
```
```console
 $ $EDITOR my-demo-pod.yaml
 $ kubectl apply -f my-demo-pod.yaml
```
```console
pod/my-demo-pod created
```

This scrap-and-replace approach to Pod updates suggests a very important feature
of Pods.  Namely that they are assumed to be ephemeral, self-contained execution
environments.  Pods are entities with fleeting lifetimes whose creation,
destruction, and recreation are routine.  This fluidity in Pod provenience is
what allows workloads based on Pods to be so resilient to service interruptions
due to hardware failures, preemption, or site outages.  However, such workloads
need to be defined in terms of groups of Pods and architected to degrade
gracefully when some subset of the group's Pods become unavailable.  For these
reasons, Pods are rarely managed directly.  Kubernetes provides several
higher-order workload kinds that orchestrate groups of pods.  These kinds manage
Pod groups according to different strategies that provide availability
characteristics that are suitable for different workload types.

#### 2 - Deployments

The most common of these kinds are `Deployments`.  Deployments manage a group of
Pods with no mutual ordering constraints.  They are typically used for
replicated stateless applications whose replicas operate completely
independently from each other.  Deployment controllers continuously monitor the
states of the deployment and the pods that they claim to manage, automatically
recreating and scheduling new pods when needed to maintain some target number of
replica Pods.

##### my-demo-deployment.yaml
```
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-demo
  # these are the labels for the deployment, proper
  labels:
    app: my-demo
    svc: web
spec:
  replicas: 1  # default, use multiple replicas for higher availability

  selector:
    # these are the labels that the deployment will use when determining
    # which pods it is supposed to manage.  Must be a subset of the
    # labels in the pod template.
    matchLabels:
      app: my-demo
      svc: web

  # when updating/upgrading, kill all existing Pods before creating new ones
  strategy:
    type: Recreate

  # this is the "kind: v1/Pod" resource from earlier, except with some redundant
  # pieces removed.
  template:

    # pod name will be provided by the deployment controller, so it is not
    # specified in the template.
    metadata:
      # labels must be a superset of the labels used by the deployment (in the
      # selector section).  This is how the deployment knows which pods "belong"
      # to it.
      labels:
        app: my-demo
        svc: web

        # The pods can optionally have other labels.
        other-label-1: one
        other-label-2: two
        other-label-3: three
        ...
    spec:
      restartPolicy: Always  # default
      nodeSelector:
        spack.io/node-pool: "base"
      containers:
        - name: my-demo-pod-container
          image: ghcr.io/spack/my-demo-image:v1.2.3

          # default for tags that do *not* end in ":latest"
          imagePullPolicy: IfNotPresent

          command: ["/usr/bin/...", "run-webserver"]
          args: ["arg-0", "arg-1", "arg-2", ...]

          ports:
            - name: http
              containerPort: 8080
              protocol: TCP

          env:
            - name: MY_ENVIRONMENT_VARIABLE_1
              value: VALUE_1
            - name: MY_ENVIRONMENT_VARIABLE_2
              value: VALUE_2
            - name: MY_ENVIRONMENT_VARIABLE_3
              value: VALUE_3
```

```console
 $ kubectl apply -f my-demo-deployment.yaml
```
```console
deployment.apps/my-demo created
```
```console
 $ kubectl get deployments my-demo
```
```console
NAME      READY   UP-TO-DATE   AVAILABLE   AGE
my-demo   1/1     1            1           2m20s
```

```console
 $ kubectl get pods
```
```console
NAME                      READY   STATUS    RESTARTS   AGE
my-demo-9c679f8dd-jxz4q   1/1     Running   0          4m21s
```

Notice how the Deployment automatically created a Pod with a generated name.

```console
 $ $EDITOR demo-deployment.yaml
 $ kubectl apply -f demo-deployment.yaml
```
```console
deployment.apps/my-demo configured
```

```console
 $ kubectl get deployments
```
```console
NAME      READY   UP-TO-DATE   AVAILABLE   AGE
my-demo   0/1     0            0           4m6s
```
```console
 $ kubectl get pods
```
```
NAME                      READY   STATUS        RESTARTS   AGE
my-demo-9c679f8dd-jxz4q   1/1     Terminating   0          4m18s
```

As a result of some change we've applied, the Deployment controllers have
automatically initiated termination of the existing Pod.  Usually, a new
replacement Pod would be created and started before the existing Pod is
terminated.  Depending on how your application is architected, existing Pods may
need to be terminated first, before their replacements are created.  In this
example, we use the `Recreate` strategy to ensure that existing Pods are
terminated before being replaced.

```console
 $ kubectl get pods
```
```console
NAME                      READY   STATUS    RESTARTS   AGE
my-demo-55ddb497f-pcgh6   1/1     Running   0          12s
```

#### 3 - Services

`Service` kinds represent a logical set of services that are backed by a set of
Pods.

##### my-demo-service.yaml
```
---
apiVersion: v1
kind: Service
metadata:
  name: my-demo
spec:
  # Only available within the cluster.  We will use ingress to expose this
  # service to external clients.
  type: ClusterIP

  # These are the labels that the service will use when determining which pods
  # to route traffic to.  Traffic sent to the service will be load balanced
  # across the selected pods.  By default, traffic is routed to a pod chosen
  # randomly among those selected.  Must be a subset of the labels in the pod
  # template.
  selector:
    app: my-demo
    svc: web

  ports:
      # name corresponds to the named port on the Pod
    - name: http

      # the logical service will be available on port 80
      port: 80

      # traffic to this service will be routed to port 8080 on the Pod
      targetPort: 8080
```

A brief note about `Service` `type`s: Most services would be of either
`LoadBalancer` or `ClusterIP` types.  `LoadBalancer` Services depend on some
external provider to provision a load balancer through which the service is
exposed (to public traffic if the load balancer is so routable).  For example,
most clusters deployed on AWS will have additional middleware controllers
configured to automatically provision an elastic load balancer for it.

#### 4 - Ingress & Certificates

For most `http` traffic, however, we will make use of an `Ingress` controller.
An Ingress controller adds a new custom resource, the "Ingress", that specifies
some subset of traffic and a target Service to direct that traffic to.  The
controller also installs its own service that is typically of type
`LoadBalancer`.

Handling `http` traffic this way offers several benefits.  First, only a single
external-facing service needs to be managed: the ingress service, itself.  The
ingress service acts as a reverse proxy for your other services, which can
remain internal to the cluster.  Second, as a reverse proxy, the ingress service
can also handle additional concerns that are common across most `http`
applications, such as SSL termination, caching, circuit breaking, and traffic
shifting.  In this example, we use the
[ingress-nginx](https://kubernetes.github.io/ingress-nginx/) controller.

We will also use another controller that is often deployed together with an
ingress controller: [cert-manager](https://cert-manager.io/).  This controller
handles the automatic provisioning and deployment of SSL certificates using the
public [Let's Encrypt](https://letsencrypt.org/) service.  A new custom
`Certificate` resource is added that we can use to have `cert-manager` request a
new certificate and store it in the form of a Kubernetes secret.  Then, in our
`Ingress` resource, we reference that secret so that the reverse proxy uses the
certificate within to serve and terminate SSL traffic.

##### my-demo-certificate.yaml
```
---
apiVersion: cert-manager.io/v1alpha2
kind: Certificate
metadata:
  name: my-demo
spec:
  # This is the name of the kubernetes secret that will be created/populated
  # with the TLS certificate.
  secretName: tls-my-demo

  # This is a reference to the "Issuer" that will handle the request.
  # This will typically be configured by your cluster administrator.
  issuerRef:
    name: letsencrypt
    kind: ClusterIssuer

  # request a certificate with this common name:
  commonName: my-demo.spack.io

  # request a certificate for these domains
  # (must contain the common name, if given):
  dnsNames:
    - my-demo.spack.io
```

##### my-demo-ingress.yaml
```
---
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  name: my-demo
spec:
  # The kubernetes secret containing the certificate.
  tls:
  - secretName: tls-my-demo

  # Match traffic based on the Host header.
  rules:
  - host: my-demo.spack.io
    http:
      paths:
        - backend:
            serviceName: my-demo
            servicePort: 80
```

#### 5 - Additional Notes

 - There are many details that are glossed over in this tutorial,.  For example:
   - How is DNS handled so that `my-demo.spack.io` actually resolves to the
     external load balancer?
   - Exactly how does the traffic route all the way from the load balancer to a
     Pod for servicing?
   - How to handle non-`http` traffic?
   - What about applications that need to persist state beyond a single Pod's
     lifecycle?
   - What other workload Kinds are there, and when might one need to prefer them
     over Deployments?
 - For answers to these questions, and to learn more about using Kubernetes in
   general, we refer you to the official [Kubernetes
   Documentation](https://kubernetes.io/docs/home/)
