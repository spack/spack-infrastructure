# Gantry K8s Deployment

Uses [Litestream](https://litestream.io) to continuously replicate the database and back it up as needed.

`terraform/modules/spack/spack_gantry.tf` encodes the Litestream configuration and manages Gantry's S3 bucket.

```
kubectl apply -f ingress.yaml
kubectl apply -f services.yaml
kubectl apply -f stateful-sets.yaml
```