# spack-secrets
The kubernetes cluster makes use of [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets). Sealed secrets are publicly defined encrypted secrets that can only be decrypted within the cluster. Once `SealedSecret` resources are applied to the cluster, the sealed secret controller unseals them, creating a regular secret (same name and namespace) containing the decrypted data.

This module contains a helper CLI to manage these secrets, as the underlying tool is not user friendly.


## Installation

First, the `kubeseal` cli must be installed. Installation instructions can be found [here](https://github.com/bitnami-labs/sealed-secrets#kubeseal).

Then to install the `spack-secrets` command, run the following:

```console
# From the top level project
pip install ./secrets
```

This command will allow you to view/update sealed secrets.

### Creating a new secret
To create a new secret, simply copy and un-comment the SealedSecret template (`k8s/production/sealed-secrets/sealed-secret-template.yaml`), or any other existing SealedSecret definition, to the intended file. Convention is to name the file containing your new sealed secrets to be named `sealed-secrets.yaml`.

### Updating a secret
Once you have a file containing one or more SealedSecret resources, you'll need to add/update its values. To do so, you can use the `spack-secrets` command as follows (replace the path to the `sealed-secrets.yaml` file below with your own):

```
spack-secrets update k8s/production/**/sealed-secrets.yaml
```

This will prompt you to select the specific secret you want to modify (if several are defined), and which key within the secret's data you want to update (or create a new entry). Then, your locally configured `$EDITOR` (defaults to vim) will be opened for you to enter the raw unencrypted value, which will be sealed, base64 encoded and placed into the file. Comments in the secrets file are not affected by the script, and are encouraged.

When using the editor, surrounding whitespace is automatically removed, to prevent accidental newlines/whitespace/etc. from being included into the secret value (as many editors automatically append a newline, for example). If this is to be avoided (i.e. if you explicity *need* to enter whitespace as the secret value), the `--value` argument can be used to specify the value of your secret.

Sealed Secrets are *write only*, and as such, cannot be read publicly from the definitions in this repository. However, if you have cluster access, you can read the secret value.
