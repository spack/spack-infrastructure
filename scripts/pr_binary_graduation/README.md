# PR Binary Graduation

This folder contains infrastructure to build a webservice that receives
web hook payloads from github regarding pull requests.  When PRs are
merged to spack develop, the binaries built over the course of that PR
are copied into the shared PR binary mirror, and the index of that mirror
is updated.

## Building the container

```console
cd <PROJECT_ROOT>/scripts/pr_binary_graduation
docker build -t scottwittenburg/pr-binary-graduation -f docker/Dockerfile .
```

## Running the stack

```console
cd docker
docker-compose up
```

