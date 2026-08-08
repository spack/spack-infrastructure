#Troubleshooting SPACK Infrastructure

This page will lay out some potential problems that can be encountered by
someone who is using the SPACK CI Infrastructure.  These issues are broken up by
 <...>

##Merge Requests
###CI Issues

####CI Run delays

The SPACK CI infrastructure is quite busy.  If the turn-around time of the CI
results is growing, consider executing the test infrastructure locally instead
of relying on the cloud infrastructure.

#####Test Locally

SPACK can locally execute each of the tests run on the CI.

`spack unit-test` will execute the known unit test objects using the pytest
library.  This command can be extended to specify a file to test.

```
spack unit-test lib/spack/spack/test/architecture.py
```

`spack style` is used to execute the four libraries for Python style checking
used in testing: `black, ` `isort`, `flake8`, and `mypy`. Additionally, for the
first two of those libraries, passing a `-f` flag will attempt to fix style
errors found during the run automatically.

####CI Test Failures

#####Test Errors that require changes

When test failures are found, look to replicate the test failure on the local
system and create an update to the pull request which fixes the failing test.
When the new commit is pushed, or an existing commit has been force pushed,
the CI infrastructure will restart the pipeline.

#####Test Errors that do not require changes

If no updates are needed, such as test failures due to timeout, users can ask
Spackbot to re-run the slate of jobs.  Commenting `spackbot run pipeline` or
`spackbot re-run pipeline` will kick off the CI again without needing to re-base
or create an additional commit.

#####CI Job exits with `137`

If a GitLab CI/CD job exits with exit code `137`, that means that the pool that
was picked for the job did not have enough memory to properly process the
pipeline.  When this occurs, make an update to the configuration for GitLab CI.
This occurs in the `share/spack/gitlab/cloud_pipelines/.gitlab-ci.yml` file.
Find the failing job and update the `tags` attribute for that job, replacing the
size string with the next level up:

  `small` -> `medium` -> `large` -> `xlarge` -> `huge`

For example
  `tags: ["spack", "public", "medium", "x86_64"]`
becomes
  `tags: ["spack", "public", "large", "x86_64"]`
