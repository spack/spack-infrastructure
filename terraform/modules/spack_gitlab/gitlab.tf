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

  # On staging, keep the protected branches (develop, releases/v*) in sync with GitHub.
  # Production does this with the gh-gl-sync CronJob instead. Staging has no
  # such job.
  # Restricted to protected branches so that pulls never touch testing-branch,
  # and with build triggers off so that a sync of thousands of upstream commits
  # doesn't kick off a protected-branch pipeline.
  import_url                     = var.deployment_name == "prod" ? "" : "https://github.com/spack/spack-packages.git"
  mirror                         = var.deployment_name == "prod" ? false : true
  only_mirror_protected_branches = var.deployment_name == "prod" ? false : true
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
  for_each = var.deployment_name == "prod" ? {} : {
    PR_MIRROR_FETCH_DOMAIN        = "s3://${var.pr_binary_mirror_bucket_name}"
    PR_MIRROR_PUSH_DOMAIN         = "s3://${var.pr_binary_mirror_bucket_name}"
    PROTECTED_MIRROR_FETCH_DOMAIN = "s3://${var.protected_binary_mirror_bucket_name}"
    PROTECTED_MIRROR_PUSH_DOMAIN  = "s3://${var.protected_binary_mirror_bucket_name}"
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
  for_each = var.deployment_name == "prod" ? {} : {
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

# pre_build.py needs access to this to request PR prefix scoped permissions
resource "gitlab_project_variable" "pr_binary_mirror_bucket_arn" {
  project = gitlab_project.spack.id
  key     = "PR_BINARY_MIRROR_BUCKET_ARN"
  value   = data.aws_s3_bucket.pr_mirror.arn
}

# pre_build.py needs access to this to request PR prefix scoped permissions
resource "gitlab_project_variable" "pr_binary_mirror_bucket_arn_spack_packages" {
  project = gitlab_project.spack_packages.id
  key     = "PR_BINARY_MIRROR_BUCKET_ARN"
  value   = data.aws_s3_bucket.pr_mirror.arn
}

# Configure retries
resource "gitlab_project_variable" "retries" {
  for_each = toset([
    # Enable retries for artifact downloads, source fetching, and cache restoration in CI jobs
    "ARTIFACT_DOWNLOAD_ATTEMPTS",
    "GET_SOURCES_ATTEMPTS",
    "RESTORE_CACHE_ATTEMPTS",
  ])

  project = gitlab_project.spack.id
  key     = each.value
  value   = "3"
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
  count = var.deployment_name != "prod" ? 1 : 0

  project = gitlab_project.spack_packages.id
  name    = gitlab_project.spack_packages.default_branch
}

resource "gitlab_branch" "spack_packages_testing" {
  count = var.deployment_name != "prod" ? 1 : 0

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
  ref = one(data.gitlab_branch.spack_packages_develop[0].commit).id
}
