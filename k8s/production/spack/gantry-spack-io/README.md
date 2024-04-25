# Gantry K8s Deployment

[Gantry](https://github.com/spack/spack-gantry) is a dynamic resource allocator for Spack CI. It is a web service and available as a [container image](https://github.com/spack/spack-gantry/pkgs/container/spack-gantry).

This deployment of Gantry uses [Litestream](https://litestream.io) to continuously replicate the database and back it up as needed on an S3 bucket. The Litestream documentation has extensive details about how it works, but it's useful to understand the basics for the purposes of this deployment:

1. A pod is created in the k8s cluster, along with a persistent volume claim that will store a copy of the SQLite database.
2. If the S3 bucket has a copy of the database, Litestream will pull it down and place it into the appropriate directory.
3. If the database does not exist, the `init-db` container executes a script that initializes a database with default tables. This is a crucial step: if we continue without a schema that the application expects, the `gantry` container will crash.
4. Once the application is running and recording, the `litestream` container will constantly upload a version of the database to the S3 bucket.

In the event that the pod dies, the persistent volume claim is deleted, or any other catostrophic event, the pod can be recreated and Litestream will grab the most recent version in S3 and redeploy it.

As noted in the stateful set configuration, only **one** replica of the deployment is supported at a time, due to inherant limitations of SQLite. Currently, Gantry does not have high resource needs, but we may migrate to a new database provider in the future.

`terraform/modules/spack/spack_gantry.tf` encodes the Litestream configuration and manages Gantry's S3 bucket.

-------

This deployment of Gantry can be done by running:

```
kubectl apply -f services.yaml
kubectl apply -f stateful-sets.yaml
```
