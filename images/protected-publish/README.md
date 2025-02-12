# Protected Publish

This directory contains tooling to copy specs from stack-specific mirrors to the top level and to examine mirror indices and report on any holes.

## Background

Spack protected pipelines are run on all protected refs, and these pipelines are organized into "stacks", each of which is defined by a spack environment.  Binaries produced by these stack-specific pipelines are stored in stack-specific mirrors.  However, we also make binaries from all stacks available in a top level mirror.

Concretely, the structure of the public `develop` mirror is as follows.  At the highest level we have:

```
aws s3 ls s3://spack-binaries/
    PRE develop-2024-03-17/
    PRE develop-2024-03-24/
    PRE develop-2024-03-31/
    PRE develop-2024-04-07/
    PRE develop-2024-04-14/
    PRE develop-2024-04-21/
    PRE develop-2024-04-28/
    PRE develop-2024-05-05/
    PRE develop/
    PRE releases/
    PRE v0.18.0/
    PRE v0.18.1/
    PRE v0.19.0/
    PRE v0.19.1/
    PRE v0.19.2/
    PRE v0.20.0/
    PRE v0.20.1/
    PRE v0.20.2/
    PRE v0.20.3/
    PRE v0.21.0/
    PRE v0.21.1/
    PRE v0.21.2/
```

Each of those prefixes correspond to a particular protected ref.  Included are prefixes for all protected *tags* (release tags as well as develop snapshots) and branches (`develop` and `releases/v*.*`).  Looking inside the `develop` prefix, we can see the top level mirror (`build_cache/` in the case of a v2 mirror, or `v3` and `blobs` in the case of a v3 mirror), along with all the stack-specific mirrors:


```
$ AWS_PROFILE=spack-llnl aws s3 ls s3://spack-binaries/develop/
    PRE aws-ahug-aarch64/
    PRE aws-ahug/
    PRE aws-isc-aarch64/
    PRE aws-isc/
    PRE aws-pcluster-icelake/
    PRE aws-pcluster-neoverse_n1/
    PRE aws-pcluster-neoverse_v1/
    PRE aws-pcluster-skylake/
    PRE aws-pcluster-x86_64_v4/
    PRE build_cache/
    PRE build_systems/
    PRE data-vis-sdk/
    PRE deprecated/
    PRE developer-tools-manylinux2014/
    PRE developer-tools/
    PRE e4s-aarch64/
    PRE e4s-arm/
    PRE e4s-cray-rhel/
    PRE e4s-cray-sles/
    PRE e4s-neoverse-v2/
    PRE e4s-neoverse_v1/
    PRE e4s-oneapi/
    PRE e4s-power/
    PRE e4s-rocm-external/
    PRE e4s/
    PRE gpu-tests/
    PRE ml-darwin-aarch64-mps/
    PRE ml-linux-x86_64-cpu/
    PRE ml-linux-x86_64-cuda/
    PRE ml-linux-x86_64-rocm/
    PRE radiuss-aws-aarch64/
    PRE radiuss-aws/
    PRE radiuss/
    PRE tutorial/
```

Mirrors for all other protected refs are organized in the same manner.

## The problem

Spacks stack-specific pipelines populate stack-specific mirrors, but users likely want access to the union of all stack-specific mirrors for a given `ref`, to improve binary cache hit-rate or other reasons.  So once pipelines have populated the stack-specific mirrors, we need to safely copy the union of those built specs to the root.  We don't want to blindly copy everything from all stacks, as much of it may already exists at the top level, and we can't use `aws s3 sync` due to the possibility of duplicated hashes among the stacks.  We also need to avoid publishing any binaries that are still signed with the intermediate ci key, since all binaries at the top level must be signed with the reputational signature produced by the `signing-job` in gitlab.

## Previous approach

The previous approach to accomplish this copying of specs from stack-specific mirrors to the top level was the `protected-publish` gitlab job that ran after all child pipelines completed successfully.  This job had to be configured to run *only* when all child pipelines completed successfully, mainly due to the risk of contaminating the top level mirror with improperly signed binaries if the `signing-job` failed.

When pipeline generation runs, it produces a manifest of everything new the pipeline will build, and this was provided via artifacts to the `protected-publish` job, so that it could only copy the new things to the top level.  One problem with the previous approach is that holes were produced in the top level mirror when any of the child pipelines failed, and thus the `protected-publish` job failed to run.  Information about exactly what was in those "holes" was scattered around in the artifacts of skipped `protected-publish` jobs.

Another problem with the previous approach is that it added too much time to each protected pipeline.  Rebuilding a mirror index can take a long time, not to mention the time to copy potentially large files from one prefix to another.  This resulted in hours extra delay before another protected pipeline could run on the same ref.

## Next approach

The `protected-publish` job will no longer exist, instead we will use an external program to publish specs from stack-specific mirrors to the top level.

The program should examine all the stack mirrors within the prefix of a ref, as well as the top level mirror, and identify any built specs which are present in at least one stack mirror, but missing from the top level mirror.  For the identified set of missing specs, the program should select any stack that has both the metadata and archive file, then download the spec metadata file and verify that it is correctly signed using the reputational key.  Assuming a proper signature, the program should copy the associated archive file as well as the metadata file into the top level mirror.  After copying all missing specs to the top level, the program should rebuild the index of the top level mirror. If the program determines there are no missing specs at the top level, it should not update the index top level index.

The program described above should be triggered to run upon completion of any protected pipline, so that the newly built specs from the pipeline are immediately published to the top level mirror.  A github webhook can be used for this purpose, but in case any key events are missed, the program can also be run as a cron job in order to perform a daily (for example) publish of all refs that saw pipeline activity that day.

This directory contains an implementation of the program as a docker image.

## Running the container

The container has three entrypoints:

1. `python -m pkg.publish` (the default) Publish stack-specific mirrors to the top level
2. `python -m pkg.validate_index` Read a mirror index and report on any missing specs (non-external specs marked as `in_buildcache: False`)
3. `python -m pkg.migrate` Migrate a v2 mirror to v3 in place

The container application assumes the structure of the mirror is as described earlier in this document.  To publish the stacks for a single ref, you must provide a bucket and a ref (e.g. `develop`).  Other options allow:

- publishing stacks for all refs that had pipelines recently
- excluding a set of stacks from publishing
- setting thread parallel level.

There are also two options useful for debugging, measuring, or otherwise examining the files produced by the container.

Some examples of running the entrypoints and options:

### See application options

To see the options available to either entrypoint, use the `--help` option:

```
docker run --rm \
    -ti protected-publish:latest \
    --help
Publish script started at 2024-05-09 22:27:27.646863
usage: publish.py [-h] [-b BUCKET] [-r REF] [-d DAYS] [-f] [-p PARALLEL] [-w WORKDIR] [-x EXCLUDE [EXCLUDE ...]]

Publish specs from stack-specific mirrors to the top level

options:
  -h, --help            show this help message and exit
  -b BUCKET, --bucket BUCKET
                        Bucket to operate on
  -r REF, --ref REF     A single protected ref to publish, or else 'recent', to publish any protected refs that had a pipeline recently
  -d DAYS, --days DAYS  Number of days to look backward for recent protected pipelines (only used if `--ref recent` is provided)
  -f, --force           Refetch files if they already exist
  -p PARALLEL, --parallel PARALLEL
                        Thread parallelism level
  -w WORKDIR, --workdir WORKDIR
                        A scratch directory, defaults to a tmp dir
  -x EXCLUDE [EXCLUDE ...], --exclude EXCLUDE [EXCLUDE ...]
                        Optional list of stacks to exclude
```

### Publish a single `ref`

To publish the specs from the `develop` stack mirrors to the top level `develop` mirror:

```
docker run --rm \
    -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
    -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"
    -ti protected-publish:latest \
    --bucket spack-binaries \
    --ref develop
```

> [!NOTE]
> As in the above example, some combinations of entrypoint/options require write permission to a bucket, so in this document, assume provision of `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` whenever needed.

### Publish multiple `ref`

To publish all refs with recent pipeline activity, use the special "ref", `recent`:

```
docker run --rm \
    -ti protected-publish:latest \
    --bucket spack-binaries \
    --ref recent
```

To indicate what you mean by recent, you can provide a number of days to look back:

```
docker run --rm \
    -ti protected-publish:latest \
    --bucket spack-binaries \
    --ref recent \
    --days 7
```

### In-place buildcache migration

A v2 buildcache differs from a v3 buildcache mostly in the layout of files within the mirror or prefix.  Thus, it is possible to copy files in such a way as to make a v2 mirror look like a v3 mirror, and this image provides a script to do that (only for s3 mirrors). The migration entrypoint takes a single positional argument, the url of the mirror to migrate in-place.

```
docker run --rm \
    -v /path/to/pgp/keys/dir:/.gnupg \
    -e GNUPGHOME=/.gnupg \
    --entrypoint python \
    -ti protected-publish:latest \
    -m pkg.migrate \
    s3://spack-binaries/develop/e4s
```

The migration functionality provided here only migrates signed specs. To that end, the signing key originally used to sign the binary packages (both the public and secret parts) must be available in your keychain in order to first verify, then update and re-sign the spec metadata files, during the migration process.

Migrating buildcaches where the Spack reputational signing key was used to sign the binaries is a little more involved, and requires cluster access:

First create the service account and pod which will allow you to get access to the key secrets (the signing key is still encrypted):

```
kubectl apply -f oneshot_service_account.yaml
kubectl apply -f oneshot_sealed_secrets.yaml
kubectl apply -f oneshot_pod.yaml
```

Find the pod you just created:

```
$ kubectl get -n custom pods
NAME                                     READY   STATUS              RESTARTS   AGE
access-node-68d4d944fd-sp9dz             0/1     ContainerCreating   0          9s
```

Wait until the `STATUS` is `Running`, and then exec on to the running pod and run the migration, providing the url of the mirror you wish to migrate:

```
kubectl exec -n custom -ti access-node-68d4d944fd-sp9dz -- /bin/bash
cd /srcs
./migrate.sh <mirror-url>
```

To clean up afterwards, first exit the pod, then delete the kube resources:

```
kubectl delete deployment -n custom access-node
kubectl delete sealedsecret -n custom spack-signing-key-encrypted
kubectl delete serviceaccount -n custom naccess
```

### Validate a buildcache index

To examine a local or remote (S3 only) index for any missing specs:

```
docker run --rm \
    --entrypoint python \
    -ti protected-publish:latest \
    -m pkg.validate_index \
    --url s3://spack-binaries/develop-2024-01-07 --version 2
```

The version is used to select whether v2 or v3 index is sought.

Optionally, instead of specifying `--url` and `--version`, you can specify a local file with `--file` followed by an absolute path.

### Options useful during development

The application retrieves an object listing from S3 and saves it to disk, and it may also download and store spec metadata files from the remote stack mirrors.  Normally the application does this in a temporary directory that is automatically cleaned up.

To examine the files produced by the application (possibly useful for debugging or measuring), you can provide the `--workdir` option.  In this case the application will use any existing working files it finds on disk (instead of downloading them again), and also it will not clean up after itself when finished.

To publish specs from stacks to the top level for a ref, while re-using preserved working files, mount a directory and provide the `--workdir` option:

```
docker run --rm \
    -v /path/on/your/host:/path/in/container
    -ti protected-publish:latest \
    --bucket spack-binaries \
    --ref develop \
    --workdir /path/in/container
```

To force re-downloading the working files while using the `--workdir` option, you can use `--force`.
