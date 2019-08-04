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
ls volumes/package-signing-key
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
     ([Workaround](#issue-private-cdash))
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
      generated earlier.  If you're not using CDash, leave the value
      empty.
   - `DOWNSTREAM_CI_REPO`:
     `http://root:<PASS>@gitlab:10080/root/spack-build.git`
   - `SPACK_RELEASE_ENVIRONMENT_REPO`:
      `http://root:<PASS>@gitlab:10080/root/spack-env.git
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
 - Browse to `localhost:8080/root/spack-mirror/-/settings/ci_cd`
 - Under "Variables"
   - Add the following variables.  Ensure that none are masked or protected.
   - `SPACK_SIGNING_KEY`: set to the base64-encoded contents of the
     signing key you generated earlier.

spack-env

 - Browse to `localhost:8080/projects/new`
 - Create a new project called "spack-env".

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
rm -rf volumes
```

Known Issues

 - <a name="issue-private-cdash"></a>
   The pre-ci phase cannot submit reports to a private CDash project.


