# The `spack` group and its projects on gitlab.staging.spack.io. These were
# originally created by hand, so the `import` blocks below adopt the existing
# objects rather than creating new ones.
#
# Note that the equivalent objects on gitlab.spack.io are still unmanaged; the
# spack_gitlab module reads them through `data` blocks instead.

resource "gitlab_group" "spack" {
  name = "spack"
  path = "spack"

  visibility_level = "public"
}

resource "gitlab_project" "spack" {
  name         = "spack"
  path         = "spack"
  namespace_id = gitlab_group.spack.id

  visibility_level = "public"
  default_branch   = "develop"
  ci_config_path   = "share/spack/gitlab/cloud_pipelines/.gitlab-ci.yml"
}

resource "gitlab_project" "spack_packages" {
  name         = "spack-packages"
  path         = "spack-packages"
  namespace_id = gitlab_group.spack.id

  visibility_level = "public"
  default_branch   = "develop"
  ci_config_path   = ".ci/gitlab/.gitlab-ci.yml"

  # Keep the protected branches (develop, releases/v*) in sync with GitHub.
  # Production does this with the gh-gl-sync CronJob instead. Staging has no
  # such job.
  #
  # Restricted to protected branches so that pulls never touch testing-branch,
  # and with build triggers off so that a sync of thousands of upstream commits
  # doesn't kick off a protected-branch pipeline.
  import_url                     = "https://github.com/spack/spack-packages.git"
  mirror                         = true
  only_mirror_protected_branches = true
  mirror_trigger_builds          = false
}

# Point the buildcache mirrors at the staging buckets. The checked-in
# .gitlab-ci.yml names the production buckets, and project variables take
# precedence over its global `variables:` block.
#
# These are set on the project rather than committed to testing-branch so that
# they also cover pipelines on develop, which would otherwise push to the
# production buildcache.
resource "gitlab_project_variable" "spack_packages_binary_mirrors" {
  for_each = {
    PR_MIRROR_FETCH_DOMAIN        = "s3://spack-binaries-prs-staging"
    PR_MIRROR_PUSH_DOMAIN         = "s3://spack-binaries-prs-staging"
    PROTECTED_MIRROR_FETCH_DOMAIN = "s3://spack-binaries-staging"
    PROTECTED_MIRROR_PUSH_DOMAIN  = "s3://spack-binaries-staging"
  }

  project = gitlab_project.spack_packages.id
  key     = each.key
  value   = each.value

  # testing-branch is not a protected branch, so these have to be available to
  # unprotected refs.
  protected = false
}

# Restrict pipelines to the build_systems stack and turn off pruning.
# Like the mirrors above, these override the values in the checked-in .gitlab-ci.yml.
resource "gitlab_project_variable" "spack_packages_pipeline_scope" {
  for_each = {
    SPACK_CI_ENABLE_STACKS = "/^.*(build_systems).*$/"
    SPACK_PRUNE_UNTOUCHED  = "False"
    SPACK_PRUNE_UP_TO_DATE = "False"
  }

  project = gitlab_project.spack_packages.id
  key     = each.key
  value   = each.value

  protected = false

  # The project-variable equivalent of the `expand: false` that
  # SPACK_CI_ENABLE_STACKS carries in .gitlab-ci.yml, needed because its value
  # contains a `$`. Harmless for the other two, whose values have none.
  raw = true
}

################################################################################
# pr1_testing-branch
#
# A stable branch of spack-packages to run staging pipelines against. Its
# contents are an unmodified copy of the default branch; everything that makes a
# staging pipeline differ from a production one comes from the project variables
# above.
#
# The branch is cut from whatever the default branch currently points at rather
# than from a pinned commit, so once the mirror above advances develop, the next
# apply recreates the branch on top of it. Anything pushed to the branch by hand
# is lost when that happens.
################################################################################

data "gitlab_branch" "spack_packages_develop" {
  project = gitlab_project.spack_packages.id
  name    = gitlab_project.spack_packages.default_branch
}

resource "gitlab_branch" "spack_packages_testing" {
  project = gitlab_project.spack_packages.id

  # The name is load-bearing. It has to match /^pr[\d]+_.*$/ for .base-job in
  # .ci/gitlab/.gitlab-ci.yml to emit any jobs at all -- those rules have no
  # fallback, so any other name produces an empty pipeline -- and it has to
  # start with "pr" to match the ref:pr* condition on the PR binary mirror role
  # in the spack_gitlab module, or the jobs cannot assume it.
  name = "pr1_testing-branch"

  # Resolving develop to a commit is what makes the branch follow it: `ref`
  # forces replacement when it changes, whereas the name "develop" would leave
  # the branch wherever it was first cut.
  ref = one(data.gitlab_branch.spack_packages_develop.commit).id
}
