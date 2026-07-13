# Runner config inconsistencies

Two inconsistencies surfaced while converting the runner `release.yaml` files to
Jsonnet (converting forces every difference between the files to be named, so
copy-paste drift stands out). Neither is known to be causing an outage today;
both are worth a deliberate fix-or-confirm.

## 1. `serviceAccountName` is set unevenly across the public tier

Under `values.runners`, `serviceAccountName: runner` is set on **all protected
runners** and on **public graviton**, but is **missing** from **public x86**
(`v2`, `v3`, `v4`) and **public windows** (`v2-win`). Within one tier, graviton
and x86 disagree, which points to copy-paste drift rather than intent.

- Present: `protected/*`, `public/graviton/{3,4}`
- Absent: `public/x86_64/{v2,v3,v4,v2-win}`, `signing` (signing uses `notary`)

**Likely implication:** low. The manager pod's service account comes from
`rbac.serviceAccountName: runner` (present in every file) and the CI job pods'
account comes from the TOML `[runners.kubernetes] service_account` (`"runner"`,
also everywhere), so the effective identities are already pinned elsewhere.
`values.runners.serviceAccountName` is most likely redundant/inert here — but the
divergence is confusing and should be made uniform (add it to the public x86 +
windows runners, or drop it from public graviton) so future readers don't infer
meaning from the difference.

## 2. The `CI_OIDC_REQUIRED` opt-out lives on only one runner, decoupled from its tag

Only `public/x86_64/v2` wraps its pre-build script in
`if [ ${CI_OIDC_REQUIRED:-1} == 1 ]; then ... fi`, letting a job skip OIDC setup.
It is also the only runner tagged `service` / `service_noop`, and per the README
`CI_OIDC_REQUIRED` is meant for `service`-tagged runners — so today this is
*consistent*, not broken.

The risk is coupling: the guard (in the pre-build TOML string) and the `service`
tag (in `runners.tags`) are set independently, in different parts of the file,
with nothing keeping them in sync.

**Likely implication:** latent maintenance hazard. If a future runner gains the
`service` tag without the guard, jobs setting `CI_OIDC_REQUIRED=0` would still be
forced through OIDC setup (silently ignoring the documented opt-out). Conversely,
adding the guard without the tag advertises an opt-out no scheduling actually
routes to. Consider deriving one from the other (e.g. a single "service runner"
flag that emits both) so they can't drift apart.
