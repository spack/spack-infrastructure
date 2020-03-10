### Setup

#### Prepare settings

```
cp vars.sh my-vars.sh
$EDITOR my-vars.sh # OPTIONAL
source my-vars.sh
```

#### Generate a key for signing packages.
```
docker-compose run --rm gen-key
ls data/package-signing-key
```

#### Deploy CDash

Start the CDash database and wait for it to report as "healthy".

```
docker-compose up -d mysql
watch 'docker-compose ps'
```

Once "healthy", ctrl-c the `watch`.

Initialize the CDash database.

```
docker-compose run --rm cdash install configure
```

Start the CDash service.

```
docker-compose up -d cdash
watch 'docker-compose ps'
```

Once "healthy", ctrl-c the `watch`.

Generate a CDash token and Create a CDash project.

 - browse to `localhost:8081/user.php`. (CDash instance)
 - login with name `root@docker.container` and cdash password
 - Under "Authentication Tokens", add a description and click
   "Generate Token".
 - Copy and save the token contents.  You will need it later.
 - Create a new project called "spack"
   - Ensure that "Public Dashboard" is checked and "Authenticate
     Submissions" is unchecked.
     ([Known Issues](#issue-private-cdash))
   - The rest of the project settings can be left at default values.

When you go to configure your spack environment for reporting jobs to this
CDash instance, set the CDash url as follows:

```
cdash:
  ...
  url: http://cdash
```

#### Deploy Gitlab and Gitlab Runners

Start the Gitlab database and Gitlab services.

```
docker-compose up -d gitlab
watch 'docker-compose ps'
```

Once the Gitlab service reports as "healthy", ctrl-c the `watch`.
This may take a few minutes.

Set the generated runner registration token.
 - browse to `localhost:8080/admin/runners`.
 - login with name `root` and gitlab password
 - Take note of the registration token under "Set up a shared
   Runner manually".

```
$EDITOR my-vars.sh # set RUNNER_REGISTRATION_TOKEN
source my-vars.sh

docker-compose up -d rdocker
```

 - After a few minutes and upon refreshing the page, a new runner should appear
   in the table below.

#### Create Gitlab Project

spack-env

 - Browse to `localhost:8080/projects/new`
 - Create a new project called "spack-env".
   - Ensure that the repository is initialized with a README.
 - Browse to `localhost:8080/root/spack-env/-/settings/ci_cd`
 - Under "Variables"
   - Add the following variables.  Ensure that none are masked or protected.
     Replace any instances of `<PASS>` with your Gitlab password.
   - `CDASH_AUTH_TOKEN`: set to the contents of the CDash token you
      generated earlier.  If you're not using CDash, set this to any
      arbitrary, non-empty value.
   - `DOWNSTREAM_CI_REPO`:
     `http://root:<PASS>@gitlab:10080/root/spack-env.git`
   - `SPACK_SIGNING_KEY`: set to the base64-encoded contents of the
     signing key you generated earlier.
   - Optional Variables:
     - `SPACK_REPO`: URL to the Spack git repo to clone.  If set, then a copy of
       Spack is fetched using the given URL.  This copy of Spack is used for
       each build job.  Otherwise, it is assumed that the runners run jobs in an
       environment with Spack pre-installed.
     - `SPACK_REF`: Version of Spack to checkout (given as a git ref).  Has no
       effect if `SPACK_REPO` is not set.
     - `AWS_ACCESS_KEY_ID`: access key id (if using an S3 mirror).
     - `AWS_SECRET_ACCESS_KEY`: secret access key (if using an S3 mirror).
     - `AWS_PROFILE`: AWS profile (if using an S3 mirror).  Can be set instead
       of `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.  Runners must be
       preconfigured with an AWS profile of the same name, and this profile must
       provide the access credentials to be used when connecting to an S3
       mirror.
     - `S3_ENDPOINT_URL`: Endpoint URL of S3 host (if using an S3 mirror not
       hosted by AWS).


#### Bring up S3-compatible storage server (optional)

This section assumes you want to test out using S3-compatible storage for
hosting your binaries.  This can safely be ignored if you prefer to use the
file system mirror described elsewhere in this document.

First bring up the service:

```
docker-compose up -d minio
watch 'docker-compose ps'
```

Once "healthy", ctrl-c the `watch`.

Navigate to "http://localhost:8083/" and log in with the name and password in
the `my-vars.sh` file.

Use the `+` button at the bottom right to create a new bucket called
`spack-public`.  To use this service as a binary mirror in your build pipelines,
the mirror url you should set will depend on the bucket name you chose.  If
using `spack-public` as the bucket name, then configure the mirror in your
release environment as follows:

```
  mirrors: { "mirror": "s3://spack-public/mirror" }
```

See the optional CI variables above for information on how to provide S3 access
credentials.  Specifically, the values for `MINIO_ACCESS_KEY` and
`MINIO_SECRET_KEY`, defined in the `my-vars.sh` file, should be used for the CI
variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, respectively.
Additionally, since this is not an AWS S3 service, you must specify an endpoint
url in your environment:

```
S3_ENDPOINT_URL="http://minio:10083"
```

#### Prepare a spack environment

```
# replace <PASS> with your gitlab password
git clone http://root:<PASS>@localhost:8080/root/spack-env.git
cd spack-env
$EDITOR spack.yaml
$EDITOR .gitlab-ci.yaml
git add .
git commit -m 'add example environment'
git push -u origin master
```

See [this repository](https://github.com/spack/spack-tutorial-container)
for an example environment repo, including more documentation on how a
custom workflow could be implemented using the spack pipelines feature.
There is also documentation on pipelines
[here](https://spack.readthedocs.io/en/latest/pipelines.html).

#### Observe the Spack Pre-CI Pipeline

 - Browse to `localhost:8080/root/spack-env/pipelines`
 - There should be a new pipeline with a single job.  The job should complete,
   and create a new pipeline with several build jobs.
   These jobs should build their respective packages, and upload them to your
   configured mirrors.

#### Review build results on CDash

 - Browse to `http://localhost:8081/index.php?project=spack`
 - You should be able to browse the results of the various build jobs.

#### Other Notes

To shutdown:
```
docker-compose down
```

To delete persistent data
```
docker-compose down --volumes
rm -rf data
```

Known Issues

 - <a name="issue-private-cdash"></a>
   The pre-ci phase cannot report build group information to a private CDash
   project.
 - Build jobs in the primary build phase cannot submit authenticated CDash
   reports.
 - Installing packages from a binary mirror may fail if the fetched
   binary needs to be relocated.
