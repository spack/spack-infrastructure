#! /usr/bin/env python

from pathlib import Path
import subprocess
import sys
import yaml


def get_yaml_path(name, namespace):
    """Returns the path to a k8s YAML file given its name and namespace."""
    for file in Path(__file__).parents[1].rglob("k8s/**/*.y*ml"):
        if "staging" in str(file):
            continue
        with open(file) as fd:
            for doc in yaml.safe_load_all(fd):
                try:
                    if (name, namespace) == (
                        doc["metadata"]["name"],
                        doc["metadata"]["namespace"],
                    ):
                        return file
                except KeyError:
                    continue
    return None


def _get_path_relative_to_k8s_directory(file_path):
    return file_path.relative_to(Path(__file__).parents[1])


def main():
    # Find all staging patches
    patch_files = list(Path(__file__).parent.parent.rglob("**/staging/**/*.y*ml"))

    # Build mapping between staging patches and the files they are applied to
    patch_file_mapping = {}
    for patch_file in patch_files:
        with open(patch_file) as fd:
            for doc in yaml.safe_load_all(fd):
                try:
                    original_name = doc["data"]["name"]
                    original_namespace = doc["metadata"]["namespace"]
                    original_yaml = get_yaml_path(original_name, original_namespace)
                    if original_yaml is None:
                        raise AssertionError(
                            f'\033[91mStaging patch "{_get_path_relative_to_k8s_directory(patch_file)}" '
                            "refers to nonexistant yaml.\033[0m"
                        )
                    patch_file_mapping[patch_file] = original_yaml
                    break
                except KeyError:
                    continue

    for patch_file, yaml_file in patch_file_mapping.items():
        print(
            f"Validating {_get_path_relative_to_k8s_directory(patch_file)} "
            f"against {_get_path_relative_to_k8s_directory(yaml_file)}...",
            end="",
        )
        if (
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).parent / "gitops-patch.py"),
                    yaml_file,
                    patch_file,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            != 0
        ):
            print("\033[91mFAILED\033[0m")
            raise AssertionError(f"\033[91m{str(patch_file)} is invalid.\033[0m")
        print("\033[92mPASSED\033[0m")

    print(f"\033[92m{len(patch_files)} patch files successfully validated.\033[0m")


if __name__ == "__main__":
    main()
