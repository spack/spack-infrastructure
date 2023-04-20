# Note about development version of spackbot

This directory contains what is basically a copy of spackbot to be used for development purposes.

The development version of the app is registered as `spack-bot-test` under the [spack-test](https://github.com/organizations/spack-test) organization.  Also, it only has access to the [spack-test/spack](https://github.com/spack-test/spack) repo.

## Workflow for testing with the development verion

To experiment with your spackbot changes, you must first temporarily disable flux from interfering with your changes.  This is accomplished by annotating the `spackbotdev-workers` and `spackbotdev-spack-io` deployments as follows:

    kubectl annotate deployment -n spack spackbotdev-spack-io kustomize.toolkit.fluxcd.io/reconcile="disabled"
    kubectl annotate deployment -n spack spackbotdev-workers kustomize.toolkit.fluxcd.io/reconcile="disabled"

Now the development/test work cycle proceeds like this:

1. make local changes to `spack/spackbot` source code
2. build, tag, and push new images for spackbot and spackbot-workers
3. edit `k8s/spack/spackbotdev-spack-io/deployments` and update the `image` of the `spec[template][spec][containers]` elements to refer to the approprate test image tags
4. run `kubectl apply -f k8s/spack/spackbotdev-spack-io/deployments`

Now you can make a new PR from your fork of `spack-test/spack` or comment on some existing one. Make sure to force push the current develop to `spack-test/spack` before testing to
avoid accidently tagging all maintainers in spack on the new/updated PRs.

Once you are happy with your changes to `spack/spackbot`, you can merge your PR on `spack/spackbot`, and updating `main` branch there will trigger new images to be tagged `latest` and pushed.  Once the tag is updated in the registry, undo your edits to the `image` tags in the development version of spackbot (replace tags with the values in production spackbot).

If, after iteratively testing changes to spack via the process above, you don't have any changes in *this* repo (`spack/spack-infrastructure`), either to the production or development spackbot directories, you will need to manually restart any untouched kubernetes resources using:

    kubectl rollout restart -n spack deployments/spackbotdev-spack-io

or:

    kubectl rollout restart -n spack deployments/spackbot-spack-io

This will ensure that the running cluster picks up the new `latest` image tags from `ghcr.io/spack`.

When you're happy with your changes, whether you need to merge any changes to this repo (`spack/spack-infrastructure`) or not, do not forget to remove the annotation telling flux to ignore the `spackbotdev` deployments.  This can be accomplished by issuing the following commands:

    kubectl annotate deployment -n spack spackbotdev-spack-io fluxcd.io/ignore-
    kubectl annotate deployment -n spack spackbotdev-workers fluxcd.io/ignore-

## Keeping development version of spackbot up to date

When changes are made to the production version of spackbot deployment
(i.e. something changes in `k8s/spack/spackbot-spack-io/`), those same
changes should likely be made to the corresponding files in
`k8s/spack/spackbotdev-spack-io/` as well.
