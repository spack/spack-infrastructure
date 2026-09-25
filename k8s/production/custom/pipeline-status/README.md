# Pipeline status page

A read-only web page that summarises the GitLab CI pipeline for a GitHub pull request:
its overall status, a per-state job count, and the jobs that failed. It exists because
GitLab's own pipeline page is slow for Spack's pipelines, which are trees of a parent
pipeline plus one child pipeline per trigger job.

* Production: <https://ci.spack.io/pipelines/>
* Staging: <https://ci.staging.spack.io/pipelines/>

The code lives in [`analytics/analytics/pipeline_status/`](../../../../analytics/analytics/pipeline_status/).

## Why this is a separate Deployment

It runs the same image as `webhook-handler`, but as its own Deployment, because it is
the only internet-facing part of the analytics project:

* public traffic cannot starve GitLab webhook processing, or vice versa;
* it runs the `analytics.settings.public` settings module, whose urlconf does not
  contain the webhook handler at all; and
* it holds no analytics-database credentials and runs no migrations.

## Security posture

The page reads GitLab's database directly, which means it **bypasses GitLab's own
authorization**. Everything below follows from that.

| Control | Where |
| --- | --- |
| Only allowlisted projects can be queried, so a private project's pipelines can never be surfaced | `PIPELINE_STATUS_ALLOWED_PROJECTS` in `analytics/settings/base.py` |
| The webhook handler is absent from this deployment's urlconf | `analytics/urls_public.py`, selected by `analytics/settings/public.py` |
| The gateway routes only the paths this page serves, so a settings mistake alone cannot expose the webhook | `httproutes.yaml` |
| Responses are cached briefly, so page traffic cannot become unbounded query load | `PIPELINE_STATUS_CACHE_SECONDS` |
| A statement timeout caps any single GitLab query | `GITLAB_DB_STATEMENT_TIMEOUT_MS` in `analytics/settings/public.py` |
| Strict CSP with no third-party origins and no inline scripts; the frontend assets are vendored, not loaded from a CDN | `analytics/pipeline_status/middleware.py` |
| HTTPS enforced, HSTS set for this host only | `analytics/settings/public.py` |
| No Kubernetes ServiceAccount token is mounted | `automountServiceAccountToken: false` |
| No analytics-database credentials; `migrate` is never run | `command:` override in `deployments.yaml` |
| Crawlers are asked, and told, to stay away | `/robots.txt` and the `X-Robots-Tag` header |

Job and branch names are attacker-influenceable — anyone can open a PR whose branch
name contains markup — so the page relies on Django's template autoescaping, with the
CSP as the backstop. Nothing user-supplied is ever interpolated into a JavaScript
expression; the Alpine job filter reads its search text from a `data-` attribute for
exactly this reason.

### Recommended follow-up: a read-only GitLab database role

The Deployment currently reads the GitLab database with the same credentials as
`webhook-handler`, taken from the `webhook-secrets` Secret. Because this deployment
only ever issues `SELECT`s, it should use a read-only role instead.

A `gitlab_ro_user` already exists for Metabase — see
[`k8s/production/metabase/gitlab_ro_user_job.yaml`](../../metabase/gitlab_ro_user_job.yaml)
and its README. That password lives in a Secret in the `gitlab` namespace, and Secrets
cannot be referenced across namespaces, so using it here means sealing a copy into the
`custom` namespace (see [`secrets/`](../../../../secrets/)) and pointing the
`GITLAB_DB_USER` / `GITLAB_DB_PASS` variables at it.

### Rate limiting

The WAF attached to `spack-gateway` applies to this hostname like any other, but it has
no rate-based rule. The short response cache is what currently bounds database load. If
the page attracts abusive traffic, add a rate-based rule scoped to this `Host` in
[`terraform/modules/spack_aws_k8s/waf.tf`](../../../../terraform/modules/spack_aws_k8s/waf.tf).

## Performance

The page answers a request with five queries, and caches the result. Finding the PR's
pipeline goes through `ci_refs` rather than prefix-filtering `p_ci_pipelines` directly,
because the database collation is not `C` and Postgres therefore cannot turn a
`LIKE 'pr123\_%'` prefix into an index range scan — see the comments in
`analytics/pipeline_status/gitlab_queries.py`.

That reasoning was verified against a local GitLab 19.3.3 schema, but **not against
production data volumes**. Worth doing once it is deployed: `EXPLAIN (ANALYZE, BUFFERS)`
the `CI_REF_IDS_QUERY` and `LATEST_PIPELINE_BY_CI_REF_QUERY` for an old PR in
`spack/spack-packages`, and confirm the planner uses
`index_ci_refs_on_project_id_and_ref_path` and a `(ci_ref_id, id DESC)` index rather
than walking the pipeline index backwards.

## Changing things

**Add a repository.** Append its `org/repo` path to
`PIPELINE_STATUS_ALLOWED_PROJECTS`. The same string is used for the GitHub repo and the
GitLab project, which works because the `gh-gl-sync` CronJobs mirror them under the same
path. Only add public projects.

**Change the hostname.** Update `hostnames` in `httproutes.yaml` and the
`ALLOWED_HOSTS` environment variable together — Django rejects a `Host` header it has
not been told about. DNS and TLS need no changes: `*.spack.io` already resolves to the
gateway's ALB and is covered by its certificate.

**Note that `https://ci.spack.io/` is deliberately not routed**, because the gateway
only matches the paths listed above. Link to `/pipelines/`.
