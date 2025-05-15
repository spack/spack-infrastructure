# TODO: convert these to resources and manage them with Terraform

data "gitlab_group" "spack" {
  full_path = "spack"
}

data "gitlab_project" "spack" {
  path_with_namespace = "${data.gitlab_group.spack.name}/spack"
}

data "gitlab_project" "scott_sidecar" {
  path_with_namespace = "scott/pipeline-experiments"
}

data "gitlab_project" "spack_packages" {
  path_with_namespace = "${data.gitlab_group.spack.name}/spack-packages"
}
