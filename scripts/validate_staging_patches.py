#! /usr/bin/env python

from pathlib import Path
import subprocess
import sys


def main():
    # Find all staging patches
    patch_files = list(Path(__file__).parent.parent.rglob("**/staging/**/*.y*ml"))

    for patch_file in patch_files:

        # Go to root of namespace directory (i.e. 'k8s/gitlab' for gitlab namespace yamls)
        current_dir = patch_file.parent
        while current_dir.parent.name != "k8s":
            current_dir = current_dir.parent

        # Run the gitops-patch.py script on each yaml in the namespace. If one of them succeeds,
        # assume it is valid.
        for file in current_dir.rglob("*.y*ml"):
            if "/staging/" in str(file):  # skip any staging yamls
                continue

            if (
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).parent / "gitops-patch.py"),
                        file,
                        patch_file,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            ):
                break
        else:
            print(f"\033[91m{str(patch_file)} is invalid.\033[0m", file=sys.stderr)
            exit(1)

    print(f"\033[92m{len(patch_files)} patch files successfully validated.\033[0m")


if __name__ == "__main__":
    main()
