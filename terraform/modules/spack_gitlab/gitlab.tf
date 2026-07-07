# TODO: convert these to resources and manage them with Terraform

data "gitlab_group" "spack" {
  full_path = "spack"
}

data "gitlab_project" "spack" {
  path_with_namespace = "${data.gitlab_group.spack.name}/spack"
}

data "gitlab_project" "spack_experiments" {
  path_with_namespace = "pipeline-experiments/spack"
}

data "gitlab_project" "spack_packages" {
  path_with_namespace = "${data.gitlab_group.spack.name}/spack-packages"
}

data "gitlab_project" "spack_packages_experiments" {
  path_with_namespace = "pipeline-experiments/spack-packages"
}

