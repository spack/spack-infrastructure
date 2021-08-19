# Note about development version of spackbot

This directory contains what is basically a copy of spackbot to be used for development purposes.

The development version of the app is registered as `spack-bot-test` under the [spack-test](https://github.com/organizations/spack-test) organization.  Also, it only has access to the [spack-test/spack](https://github.com/spack-test/spack) repo.

## Workflow for testing with the development verion

1. make local changes to `spack/spackbot` source code
2. build, tag, and push new images for spackbot and spackbot-workers
3. edit `k8s/spack/spackbotdev-spack-io/deployments` and update the `image` of the `spec[template][spec][containers]` elements to refer to the approprate test image tags
4. run `kubectl apply -f k8s/spack/spackbotdev-spack-io/deployments`

Now you can make a new PR from your fork of `spack-test/spack` or comment on some existing one.

Once you are happy with your changes to `spack/spackbot`, you can merge your PR on `spack/spackbot`, and updating `main` branch there will trigger new images to be tagged `latest` and pushed.  Once the tag is updated in the registry, undo your edits to the `image` tags in the development version of spackbot (replace tags with the values in production spackbot).

## Keeping development version of spackbot up to date

When changes are made to the production version of spackbot deployment
(i.e. something changes in `k8s/spack/spackbot-spack-io/`), those same
changes should likely be made to the corresponding files in
`k8s/spack/spackbotdev-spack-io/` as well.
