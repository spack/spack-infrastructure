---
name: update-sealed-secret
description: Update, rotate, or add a value in a SealedSecret under k8s/**/sealed-secrets.yaml. Use when asked to rotate/update a secret or password, seal a new value, add a key to an existing sealed secret, create a new SealedSecret, or debug a secret the sealed-secrets controller cannot decrypt.
---

# Update a sealed secret

Secrets in this repo are [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets): `SealedSecret`
resources committed in the clear, which the in-cluster controller decrypts into a real `Secret` of the same
name and namespace. `secrets/README.md` documents the human workflow (`spack-secrets update`); that CLI is
curses- and `$EDITOR`-driven, so **an agent cannot drive it** — use the non-interactive `kubeseal` path below,
which does exactly what the CLI does.

## Preflight

1. **Pick the cluster that matches the file's path.** The encrypted value is only decryptable by the cluster
   whose cert sealed it.

   ```bash
   kubectl config current-context
   ```
   Switching contexts is the user's call — ask before running `kubectl config use-context`.

2. **`kubeseal` must be installed** (`which kubeseal`). If missing, stop and point the user at the
   [install instructions](https://github.com/bitnami-labs/sealed-secrets#kubeseal); do not try to work around it.

3. **Locate the target.** Sealed secrets live in `sealed-secrets.yaml` files next to the workload that uses
   them (`k8s/production/gitlab/`, `k8s/production/custom/gh-gl-sync/`, …). Read the file and note the exact
   `metadata.name`, `metadata.namespace`, and the key under `spec.encryptedData` you're changing. Files hold
   several `---`-separated `SealedSecret` docs; make sure you have the right one.

## Sealing a value

Nothing in this repo uses cluster-wide or namespace-wide scope, so every value is sealed **strict**: the
ciphertext is bound to the exact namespace *and* name. Get either wrong and the file looks fine, the commit
merges, and the controller silently fails to unseal (visible only in
`kubectl logs -n kube-system deploy/sealed-secrets-controller`).

```bash
.claude/skills/update-sealed-secret/scripts/seal-value.sh --namespace <ns> --name <secret-name>
```

The script reads the plaintext on stdin, fetches the cluster's newest active sealing cert, and prints the
ciphertext. Equivalent by hand:

```bash
kubectl get secrets -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key=active --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].data.tls\.crt}' | base64 -d > /tmp/sealing-cert.pem
printf '%s' "$VALUE" | kubeseal --raw --scope strict --namespace <ns> --name <secret-name> --cert /tmp/sealing-cert.pem
```

Use the *newest* key pair (`--sort-by` + `[-1:]`) — the controller rotates keys every 30 days and keeps old
ones for decryption only.

### Handling the plaintext

**Run the seal step yourself.** The plaintext will appear in the tool call and the transcript; that is an
accepted tradeoff for this repo, so don't hand the step back to the user or ask for permission on that basis.

```bash
printf '%s' 'the-plaintext-value' | .claude/skills/update-sealed-secret/scripts/seal-value.sh --namespace <ns> --name <secret-name>
```

Pipe the value on stdin as above rather than passing it as an argument, so it doesn't sit in the sealing
process's `ps` output. If you're generating a fresh credential (a rotation with no upstream-supplied value),
generate and seal it in one command so it exists in exactly one place:

```bash
openssl rand -base64 32 | tr -d '\n' | tee /dev/stderr | .claude/skills/update-sealed-secret/scripts/seal-value.sh --namespace <ns> --name <secret-name>
```

Two things still hold: never write plaintext into a file under the repo, and delete any scratch file that held
it once you're done.

## Editing the YAML

Replace only the ciphertext for the one key, with `Edit`:

```yaml
spec:
  encryptedData:
    postgresql-password:
      AgB2Z+OYbcCslmb01M...      # new value, on a single unwrapped line
```

- The value must be **one physical line**. A plain YAML scalar split across lines folds with a space inserted,
  which corrupts the base64 and breaks decryption.
- Either `key: <value>` or `key:` + indented continuation line is valid; match whatever the file already does.
- Leave everything else alone: comments, key order, the `template.metadata.annotations` block
  (`kustomize.toolkit.fluxcd.io/reconcile: disabled`, `sealedsecrets.bitnami.com/managed: "true"`), and the
  other keys' ciphertexts. Re-sealing rotates the session key, so an unnecessarily re-sealed key shows up as a
  spurious diff.

Adding a **new key** to an existing secret is the same, just a new entry under `encryptedData`. For a **new
SealedSecret**, copy `k8s/production/sealed-secrets/sealed-secret-template.yaml` (uncomment it) or an existing
doc, keep the two `template.metadata.annotations`, and make sure the file is picked up by the directory's
`kustomization.yaml`.

## Verify before committing

```bash
git --no-pager diff -- <file>          # exactly one key's value changed, nothing else
```

Optional round-trip check — decrypts with the cluster's private key and prints the resulting `Secret` with its
data base64-encoded, i.e. it reveals the value. Only run it if the user asks, and delete the key file after:

```bash
kubectl get secrets -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key=active --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].data.tls\.key}' | base64 -d > /tmp/recovery.pem
kubeseal --recovery-unseal --recovery-private-key /tmp/recovery.pem < single-doc.yaml   # takes one doc, not the multi-doc file
rm /tmp/recovery.pem
```

## After merging

Flux tracks `main` and reconciles `./k8s/production/` (poll 1m, interval 10m), so the change only takes effect
once merged — a branch commit does nothing. To force it: `flux reconcile kustomization flux-system --with-source`.

Then check the controller accepted it:

```bash
kubectl get secret -n <ns> <secret-name> -o jsonpath='{.metadata.resourceVersion}'
kubectl logs -n kube-system deploy/sealed-secrets-controller --tail=50   # on failure
```

Pods that consume the secret as env vars or mounted files **do not** pick up the new value automatically; the
workload needs a restart (`kubectl rollout restart deploy/<name> -n <ns>`). That's a mutating command — confirm
with the user first, and check whether the credential also needs rotating at the source (Terraform, the
database, the upstream provider) so the two don't drift apart.
