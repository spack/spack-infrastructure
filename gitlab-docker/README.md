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

#### Deploy CDash (OPTIONAL)

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

docker-compose up -d rshell rdocker
```

 - After a few minutes and upon refreshing the page, two new runners
   should appear in the table below.

#### Create Gitlab Projects

spack-mirror

 - Browse to `localhost:8080/projects/new`
 - Create a new project called "spack-mirror".
   - Ensure that the repository is initialized with a README.
 - Browse to `localhost:8080/root/spack-mirror/edit`
 - Under "Visibility, project features, permissions"
   - Disable issues
   - Disable merge requests
   - Disable git large file storage
   - Disable wiki
   - Disable snippets
   - Ensure that pipelines are *enabled*
   - Click "Save Changes"
 - Browse to `localhost:8080/root/spack-mirror/-/settings/repository`
 - Under "Protected Branches"
   - Click the "Unprotect" button for the "master" branch and
     confirm.
 - Browse to `localhost:8080/root/spack-mirror/-/settings/ci_cd`
 - Under "General pipelines"
   - Ensure that the "git fetch" strategy is selected.
   - Set the "Git shallow clone" value to 1.
   - Disable "Public pipelines" access.
   - Click "Save Changes"
 - Under "Variables"
   - Add the following variables.  Ensure that none are masked or protected.
     Replace any instances of `<PASS>` with your Gitlab password.
   - `CDASH_AUTH_TOKEN`: set to the contents of the CDash token you
      generated earlier.  If you're not using CDash, set this to any
      arbitrary, non-empty value.
   - `DOWNSTREAM_CI_REPO`:
     `http://root:<PASS>@gitlab:10080/root/spack-build.git`
   - `SPACK_RELEASE_ENVIRONMENT_REPO`:
      `http://root:<PASS>@gitlab:10080/root/spack-env.git`
   - `SPACK_RELEASE_ENVIRONMENT_PATH`: `example`, or if different,
     the directory under your environment repo that contains the
     `spack.yaml` file.


spack-build

 - Browse to `localhost:8080/projects/new`
 - Create a new project called "spack-build".
   - Ensure that the repository is initialized with a README.
 - Browse to `localhost:8080/root/spack-build/edit`
 - Under "Visibility, project features, permissions"
   - Disable issues
   - Disable merge requests
   - Disable git large file storage
   - Disable wiki
   - Disable snippets
   - Ensure that pipelines are *enabled*
   - Click "Save Changes"
 - Browse to `localhost:8080/root/spack-build/-/settings/repository`
 - Under "Protected Branches"
   - Click the "Unprotect" button for the "master" branch and
     confirm.
 - Browse to `localhost:8080/root/spack-build/-/settings/ci_cd`
 - Under "Variables"
   - Add the following variables.  Ensure that none are masked or protected.
   - `SPACK_SIGNING_KEY`: set to the base64-encoded contents of the
     signing key you generated earlier.

spack-env

 - Browse to `localhost:8080/projects/new`
 - Create a new project called "spack-env".

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

Use the `+` button at the bottom right to create a new bucket called `spack-public`.
To use this service as a binary mirror in your build pipelines, the mirror url
you should set will depend on the bucket name you chose.  If using `spack-public`
as the bucket name, then configure the mirror in your release environment as
follows:

```
  mirrors: { "mirror": "s3://spack-public/mirror" }
```

Use of S3 for binary mirror requires access credentials, which should be supplied
via environment variables available to your build jobs.  Navigate to
`localhost:8080/root/spack-build/-/settings/ci_cd`, and under "Variables", set
up the following:

```
AWS_ACCESS_KEY_ID=minio
AWS_SECRET_ACCESS_KEY=minio123
```

Substitute whatever values you provided for `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`
in the `docker-compose.yml` file.  Additionally, since this is not an AWS S3 service,
the `boto3` module requires that you specify an endpoint url in your environment.  In
this case, your build jobs will need another environment variable to provide it:

```
AWS_ENDPOINT_URL="http://minio:9000"
```

#### Prepare a spack environment

```
# replace <PASS> with your gitlab password
git clone http://root:<PASS>@localhost:8080/root/spack-env.git
cd spack-env
mkdir example
$EDITOR example/spack.yaml
git add .
git commit -m 'add example environment'
git push -u origin master
```

See [https://github.com/opadron/spack-env](https://github.com/opadron/spack-env)
for `spack.yaml` examples.

#### Push a branch to the Spack Mirror Project

```
git clone git://github.com/opadron/spack.git
cd spack
# replace <PASS> with your gitlab password
git remote add gitlab \
    http://root:<PASS>@localhost:8080/root/spack-mirror.git
git checkout ecp-testing
git push gitlab ecp-testing
```

#### Observe the Spack Pre-CI Pipeline

 - Browse to `localhost:8080/root/spack-mirror/pipelines`
 - There should be a new pipeline with a single job.  The job should complete
 - Browse to `localhost:8080/root/spack-build/pipelines`
 - There should be a new pipeline with several build jobs.
   These jobs should build their respective packages, and upload them to a
   binary mirror on the runners' local filesystem.

#### Browse the contents of the binary mirror

```
docker-compose up -d nginx
```

 - Browse to `localhost:8082`
 - You should be able to browse the contents of the binary mirror.

#### Review build results on CDash

 - Browse to `http://localhost:8081/index.php?project=spack`
 - You should be able to browse the results of the various build jobs.

#### Run the spack install demo

```
docker-compose run --rm spack-install-demo
```

The demo will install readline twice: first from source, and then from the
binary mirror.  The installation from the binary mirror should be significantly
faster.


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
 - Under certain conditions, the pre-ci phase may fail to clone a spack
   environment repo and/or fail to push to the downstream repo.

