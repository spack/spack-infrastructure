
## Introduction

Create a trigger on a repo enabled with CI/CD to open the possibility of making an API call on that repo which kicks off a pipeline.  You can pass any variables you want in the API request, and those will be available in the environment when the job runs.

### Steps

1. Create a new repo with the name `triggers`, and initialize it with a readme.  Optionally disable "Auto Dev Ops".

2. At the root of the project, add a `.gitlab-ci.yml` with a single job:

```
job1:
  tags:
    - shell
  script:
    - echo "env contains SPACK_REPO=${SPACK_REPO}"
```

3. Go to "Settings" -> "CI/CD" and expand "Pipeline triggers".  Type in a short description and click "Add trigger"

4. Copy the trigger token and export it into an environment variable, e.g. `GITLAB_TRIGGER_TOKEN`, in your environment:

```
export GITLAB_TRIGGER_TOKEN=<copy-pasted-token>
```

It's a secret, so don't echo it or anything.

5. Issue a POST request from the command line to trigger a generic pipeline on `master`:

```
curl -X POST \
     -F token=${GITLAB_TRIGGER_TOKEN} \
     -F ref=master \
     http://gitlab:10080/api/v4/projects/4/trigger/pipeline
```

Look through the output to see that variable was not available when the job ran:

```
$ echo "env contains SPACK_REPO=${SPACK_REPO}"
env contains SPACK_REPO=
```

Then try a pipeline with an arbitrary, useful variable:

```
curl -X POST \
     -F token=${GITLAB_TRIGGER_TOKEN} \
     -F ref=master http://beast.kitware.com:8080/api/v4/projects/4/trigger/pipeline \
     -F "variables[SPACK_REPO]=https://github.com/spack/spack.git"
```

and see that you have that variable available when the job runs:

```
$ echo "env contains SPACK_REPO=${SPACK_REPO}"
env contains SPACK_REPO=https://github.com/spack/spack.git
```
