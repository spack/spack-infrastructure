resource "gitlab_group" "spack" {
  name = "spack"
  path = "spack"

  visibility_level = "public"
}

# NOTE: On a fresh deployment, this project (and the other projects in this
# module) requires a one-time manual step before it can fully converge.
#
# We set initialize_with_readme = true because otherwise the project is created
# with no branches at all, including the default branch. However, GitLab creates
# that initial branch as a protected branch, and the pull mirror is configured
# with mirror_overwrites_diverged_branches = true so that the default branch can
# be force-overwritten from upstream. The README commit guarantees the branch is
# diverged from upstream, so the mirror must overwrite it, and it cannot do that
# while the branch is protected.
#
# So the first apply will fail. To resolve it, go into the project's settings in
# the GitLab UI, delete the branch protection rule on the default branch, and
# then re-run the apply.
resource "gitlab_project" "spack" {
  name         = "spack"
  path         = "spack"
  namespace_id = gitlab_group.spack.id

  # This setting is required so that the repo creates the default branch.
  # It will be wiped when the mirror happens, due to the
  # mirror_overwrites_diverged_branches setting on the pull mirror.
  initialize_with_readme = true

  visibility_level = "public"
  default_branch   = "develop"
  ci_config_path   = ".ci/gitlab-ci.yml"
}

# On staging, keep the protected branches (develop, releases/v*) in sync with GitHub.
# Production does this with the gh-gl-sync CronJob instead. Staging has no
# such job.
resource "gitlab_project_pull_mirror" "github_spack" {
  count = var.deployment_name != "prod" ? 1 : 0

  project                             = gitlab_project.spack.id
  url                                 = "https://github.com/spack/spack.git"
  only_mirror_protected_branches      = false
  mirror_trigger_builds               = false
  mirror_overwrites_diverged_branches = true
}


# NOTE: See the above comment about intended failure on first apply.
resource "gitlab_project" "spack_packages" {
  name         = "spack-packages"
  path         = "spack-packages"
  namespace_id = gitlab_group.spack.id

  # This setting is required so that the repo creates the default branch.
  # It will be wiped when the mirror happens, due to the
  # mirror_overwrites_diverged_branches setting on the pull mirror.
  initialize_with_readme = true

  visibility_level = "public"
  default_branch   = "develop"
  ci_config_path   = ".ci/gitlab/.gitlab-ci.yml"
}

# On staging, keep the protected branches (develop, releases/v*) in sync with GitHub.
# Production does this with the gh-gl-sync CronJob instead. Staging has no
# such job.
# Restricted to protected branches so that pulls never touch testing-branch,
# and with build triggers off so that a sync of thousands of upstream commits
# doesn't kick off a protected-branch pipeline.
resource "gitlab_project_pull_mirror" "github_spack_packages" {
  count = var.deployment_name != "prod" ? 1 : 0

  project                             = gitlab_project.spack_packages.id
  url                                 = "https://github.com/spack/spack-packages.git"
  only_mirror_protected_branches      = false
  mirror_trigger_builds               = false
  mirror_overwrites_diverged_branches = true
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
# testing-branch sync
#
# A tiny project whose only content is a scheduled job that force-pushes
# spack-packages' default branch onto pr1_testing-branch. It lives here rather
# than in spack-packages because that project's ci_config_path points at the
# mirrored .ci/gitlab/.gitlab-ci.yml, and a schedule cannot override it.
################################################################################

resource "gitlab_project" "testing_branch_sync" {
  count = var.deployment_name != "prod" ? 1 : 0

  name         = "testing-branch-sync"
  path         = "testing-branch-sync"
  namespace_id = gitlab_group.spack.id

  initialize_with_readme = true
  default_branch         = "main"
  visibility_level       = "public"
}

resource "tls_private_key" "testing_branch_sync" {
  count = var.deployment_name != "prod" ? 1 : 0

  algorithm = "ED25519"
}

# No expires_at, so this never needs rotating.
resource "gitlab_deploy_key" "testing_branch_sync" {
  count = var.deployment_name != "prod" ? 1 : 0

  project  = gitlab_project.spack_packages.id
  title    = "testing-branch-sync"
  key      = tls_private_key.testing_branch_sync[0].public_key_openssh
  can_push = true
}

# Base64-encoded because a masked CI variable cannot contain newlines, and an
# OpenSSH private key is multi-line. The job decodes it.
resource "gitlab_project_variable" "testing_branch_sync_key" {
  count = var.deployment_name != "prod" ? 1 : 0

  project = gitlab_project.testing_branch_sync[0].id
  key     = "SYNC_SSH_KEY"
  value   = base64encode(tls_private_key.testing_branch_sync[0].private_key_openssh)
  masked  = true
}

resource "gitlab_repository_file" "testing_branch_sync_ci" {
  count = var.deployment_name != "prod" ? 1 : 0

  project        = gitlab_project.testing_branch_sync[0].id
  branch         = gitlab_project.testing_branch_sync[0].default_branch
  file_path      = ".gitlab-ci.yml"
  encoding       = "text"
  commit_message = "Managed by Terraform"
  author_name    = "Terraform"
  author_email   = "terraform@spack.io"

  # The group runners register with runUntagged: false, so the job has to
  # name tags. These match the public x86_64 runners.
  content = <<-YAML
    sync-testing-branch:
      tags: [x86_64, small, public, spack, aws]
      image: python:3.12-alpine  # Needs python3
      rules:
        - if: $CI_PIPELINE_SOURCE == "schedule"
      script:
        - apk add --no-cache git openssh-client
        - mkdir -p ~/.ssh && chmod 700 ~/.ssh
        - echo "$SYNC_SSH_KEY" | base64 -d > ~/.ssh/id_ed25519
        - chmod 600 ~/.ssh/id_ed25519
        - ssh-keyscan ${local.gitlab_ssh_host} >> ~/.ssh/known_hosts
        - git clone --depth 1 --branch ${gitlab_project.spack_packages.default_branch}
            "ssh://git@${local.gitlab_ssh_host}/${gitlab_project.spack_packages.path_with_namespace}.git" repo
        - cd repo
        - git push --force origin HEAD:refs/heads/pr1_testing-branch
  YAML
}

resource "gitlab_pipeline_schedule" "testing_branch_sync" {
  count = var.deployment_name != "prod" ? 1 : 0

  project       = gitlab_project.testing_branch_sync[0].id
  description   = "Force-push spack-packages develop onto pr1_testing-branch"
  ref           = "refs/heads/${gitlab_project.testing_branch_sync[0].default_branch}"
  cron          = "0 */6 * * *" # Run the testing branch sync job every 6 hours
  cron_timezone = "Etc/UTC"
}
