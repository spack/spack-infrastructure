# !/usr/bin/python

import json
import os
import re
from pathlib import Path
from subprocess import PIPE, Popen

import yaml
from kubernetes import client, config

secrets_files = []
for root, dirs, files in os.walk(".", topdown=True):
    for name in files:
        if re.match("secret.+dummy", name):
            secrets_files.append(os.path.join(root, name))


SEALED_SECRETS_CERT = os.getenv("SEALED_SECRETS_CERT")
if SEALED_SECRETS_CERT is None:
    raise "Please specify cert file via SEALED_SECRETS_CERT environment variable."
if not Path(SEALED_SECRETS_CERT).exists():
    raise f"Cert file {SEALED_SECRETS_CERT} not found"

config.load_kube_config()
v1 = client.CoreV1Api()


saved_secrets = []
secrets_files = sorted(secrets_files)
for file in secrets_files:
    sealed_secret_file = parent = Path(file).parent / "sealed-secrets.yaml"

    print("--------", file)
    with open(file) as f:
        secrets = list(
            yaml.safe_load_all(
                "".join(
                    [
                        # Uncomment secrets
                        line[2:] if line.startswith("# ") else line
                        for line in f.readlines()
                    ]
                )
            )
        )

    sealed_secrets_docs = []
    for secret_dict in secrets:
        name = secret_dict["metadata"]["name"]
        namespace = secret_dict["metadata"]["namespace"]
        secret = v1.read_namespaced_secret(name=name, namespace=namespace)

        # Save
        saved_secrets.append(secret.to_dict())

        secret_dict["data"] = secret.data
        if "stringData" in secret_dict:
            del secret_dict["stringData"]

        p = Popen(["kubeseal", "--format", "yaml"], stdin=PIPE, stdout=PIPE)
        output, err = p.communicate(json.dumps(secret_dict).encode("utf-8"))
        rc = p.returncode
        if rc != 0:
            raise f"Error processing entry in {file}"

        sealed_secrets_docs.append(yaml.safe_load(output))

    # Add all docs to new file
    with open(sealed_secret_file, "w") as outfile:
        yaml.safe_dump_all(sealed_secrets_docs, outfile)


# Write out all secrets
with open("all-secrets.json", "w") as _out:
    json.dump(saved_secrets, _out)
