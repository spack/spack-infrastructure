# Gantry K8s Deployment

Requires an S3 bucket with the name `gantry` to be created in order to store database.

Uses [Litestream](https://litestream.io) to continuously replicate the database and back it up as needed.

```
kubectl create configmap litestream --from-file=litestream-config.yaml
kubectl apply -f ingress.yaml
kubectl apply -f services.yaml
kubectl apply -f stateful-sets.yaml
```