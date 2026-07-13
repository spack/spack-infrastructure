#!/usr/bin/env python3
"""Compare a rendered runner manifest (stdin) with its release.yaml (argv[1]).

Equivalence ignores YAML formatting (key order, quoting, comments) and, inside
the runner `config`, TOML indentation and blank lines within embedded scripts --
none of which affect what GitLab or Kubernetes actually do.
"""
import sys, io, tomllib, yaml


def norm(stream):
    docs = list(yaml.safe_load_all(stream))
    for d in docs:
        try:
            cfg = d["spec"]["values"]["runners"]["config"]
        except (KeyError, TypeError):
            continue
        toml = tomllib.loads(cfg)
        for runner in toml.get("runners", []):
            for k, v in runner.items():
                if k.endswith("_script"):
                    runner[k] = [ln.strip() for ln in v.splitlines() if ln.strip()]
        d["spec"]["values"]["runners"]["config"] = toml
    return docs


rendered = norm(sys.stdin)
with open(sys.argv[1]) as f:
    original = norm(f)
sys.exit(0 if rendered == original else 1)
