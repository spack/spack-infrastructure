from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml


def _gen_kustomization_manifest(resources: list[str]):
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": resources,
    }


def main():
    prod_directory = Path(__file__).parents[1] / "k8s" / "production"
    staging_directory = Path(__file__).parents[1] / "k8s" / "staging"
    top_level_directories = defaultdict(list)

    for manifest in prod_directory.rglob("*.y*ml"):
        if manifest.name.startswith("kustomization.") or manifest.name.startswith(
            "secret"
        ):
            continue
        rel_path = manifest.relative_to(prod_directory)
        namespace_dir = str(rel_path).split("/")[0]
        rel_path = "/".join(str(rel_path).split("/")[1:])
        rel_path = '../../production/' + namespace_dir + '/' + rel_path
        top_level_directories[namespace_dir].append(rel_path)

    for dir, manifests in top_level_directories.items():
        kustomization = _gen_kustomization_manifest(manifests)
        file_path = staging_directory / dir / "kustomization.yaml"
        if file_path.exists():
            print(f'{file_path} already exists, skipping...')
            continue

        file_path.parent.mkdir(exist_ok=True)
        file_path.write_text(yaml.dump(kustomization))


if __name__ == "__main__":
    main()
