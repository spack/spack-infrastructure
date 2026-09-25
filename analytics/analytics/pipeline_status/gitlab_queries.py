"""Read-only queries against GitLab's own database.

The GitLab pipeline page is slow for Spack's pipelines, largely because a Spack
pipeline is a tree: a small parent pipeline whose trigger ("bridge") jobs each
create a child pipeline holding the actual package builds. Rendering a useful
summary through the API means walking that tree over many requests.

Going straight to the database lets us answer the same question in a handful of
queries. Everything here is strictly read-only, and is deliberately expressed as
raw SQL rather than Django models: this is GitLab's schema, not ours, so there is
nothing for us to migrate and nothing that should tempt us into writing to it.

Schema notes (GitLab 19.x), since the column names are not self-explanatory:
  * `p_ci_builds.commit_id` is the *pipeline* id, not a git commit.
  * `p_ci_builds.type` is 'Ci::Build' for a normal job and 'Ci::Bridge' for a
    trigger job that spawns a child pipeline.
  * `p_ci_builds.retried` is true for superseded attempts of a retried job.
  * `ci_sources_pipelines` links a child pipeline (`pipeline_id`) to its parent
    (`source_pipeline_id`), and to the bridge job that created it (`source_job_id`).
  * the CI tables are partitioned on `partition_id`; a child pipeline and its jobs
    share the partition of the pipeline, so passing the partition ids we already
    know lets Postgres prune partitions instead of scanning all of them.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from cachetools import TTLCache, cached
from django.db import connections

from analytics.core.gitlab_enums import FAILURE_REASON_MAP

# Resolve a project's numeric id from its full path. GitLab keeps the full path in
# `routes` rather than on `projects` itself.
PROJECT_ID_QUERY = """
SELECT source_id
FROM routes
WHERE source_type = 'Project'
  AND path = %(path)s
"""

# Resolving the PR's branch through `ci_refs` first is what keeps this page fast.
#
# We only know the ref's prefix, and the database collation is not "C", so Postgres
# will not turn `ref LIKE 'pr123\\_%'` into an index range scan -- it has to filter
# rows instead. Doing that filtering on `p_ci_pipelines` means walking that project's
# pipelines newest-first until a match turns up, which for an older PR is a lot of
# index entries. `ci_refs` holds one row per branch rather than one per pipeline, so
# the same prefix filter there is cheap, and it hands back a `ci_ref_id` for which
# p_ci_pipelines has a (ci_ref_id, id DESC) index.
CI_REF_IDS_QUERY = """
SELECT id
FROM ci_refs
WHERE project_id = %(project_id)s
  AND ref_path LIKE %(ref_path_pattern)s
"""

# The most recent top-level pipeline for a known ci_ref. "Top-level" matters because
# child pipelines share their parent's ref, so an unfiltered ORDER BY id DESC would
# happily return a child.
LATEST_PIPELINE_BY_CI_REF_QUERY = """
SELECT
    p.id,
    p.ref,
    p.sha,
    p.status,
    p.partition_id,
    p.created_at,
    p.started_at,
    p.finished_at,
    p.duration
FROM p_ci_pipelines p
WHERE p.ci_ref_id = ANY(%(ci_ref_ids)s)
  AND NOT EXISTS (
      SELECT 1
      FROM ci_sources_pipelines csp
      WHERE csp.pipeline_id = p.id
  )
ORDER BY p.id DESC
LIMIT 1
"""

# Fallback for pipelines that predate -- or for whatever reason lack -- a ci_ref. Same
# result, but it has to filter on `ref` itself. See CI_REF_IDS_QUERY above.
LATEST_PIPELINE_QUERY = """
SELECT
    p.id,
    p.ref,
    p.sha,
    p.status,
    p.partition_id,
    p.created_at,
    p.started_at,
    p.finished_at,
    p.duration
FROM p_ci_pipelines p
WHERE p.project_id = %(project_id)s
  AND p.ref LIKE %(ref_pattern)s
  AND NOT EXISTS (
      SELECT 1
      FROM ci_sources_pipelines csp
      WHERE csp.pipeline_id = p.id
  )
ORDER BY p.id DESC
LIMIT 1
"""

# Walk the pipeline tree downwards from the parent. UNION (not UNION ALL) so that
# a cycle -- which should be impossible, but this is not our schema to guarantee --
# terminates instead of spinning.
PIPELINE_TREE_QUERY = """
WITH RECURSIVE descendants AS (
        SELECT %(root_id)s::bigint AS pipeline_id
    UNION
        SELECT csp.pipeline_id
        FROM ci_sources_pipelines csp
        JOIN descendants d ON csp.source_pipeline_id = d.pipeline_id
)
SELECT
    p.id,
    p.status,
    p.partition_id,
    p.created_at,
    p.started_at,
    p.finished_at,
    p.duration
FROM descendants d
JOIN p_ci_pipelines p ON p.id = d.pipeline_id
ORDER BY p.id
"""

# How many jobs are in each state across the whole tree. Superseded attempts of a
# retried job are excluded so that the counts describe the pipeline as it stands
# now rather than everything that was ever run.
JOB_STATUS_COUNTS_QUERY = """
SELECT
    b.status,
    COUNT(*) AS count
FROM p_ci_builds b
WHERE b.commit_id = ANY(%(pipeline_ids)s)
  AND b.partition_id = ANY(%(partition_ids)s)
  AND COALESCE(b.retried, FALSE) = FALSE
GROUP BY b.status
"""

# The failed jobs themselves. Trigger jobs are included -- a failed trigger means a
# whole child pipeline never ran, which is exactly what someone debugging a PR
# needs to see -- and are distinguished by `type` so the template can label them.
FAILED_JOBS_QUERY = """
SELECT
    b.id,
    b.name,
    b.type,
    b.failure_reason,
    b.allow_failure,
    b.commit_id AS pipeline_id,
    b.started_at,
    b.finished_at,
    s.name AS stage_name,
    s.position AS stage_position
FROM p_ci_builds b
LEFT JOIN p_ci_stages s ON s.id = b.stage_id
WHERE b.commit_id = ANY(%(pipeline_ids)s)
  AND b.partition_id = ANY(%(partition_ids)s)
  AND COALESCE(b.retried, FALSE) = FALSE
  AND b.status = 'failed'
ORDER BY b.allow_failure, s.position NULLS LAST, b.name
LIMIT %(limit)s
"""

# Job states GitLab considers finished-and-unsuccessful vs. still-in-flight. Used to
# summarise a tree of pipelines into a single headline number.
FAILED_STATUSES = frozenset({"failed"})
IN_PROGRESS_STATUSES = frozenset(
    {"created", "waiting_for_resource", "preparing", "pending", "running", "scheduled"}
)

# A pipeline with more failed jobs than this is already telling you what you need to
# know, and rendering thousands of rows would defeat the point of a fast page.
FAILED_JOBS_LIMIT = 500


@dataclass(frozen=True)
class Pipeline:
    """A single GitLab pipeline -- either the PR's parent pipeline or one of its children."""

    id: int
    status: str
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    duration: int | None

    @property
    def elapsed_seconds(self) -> int | None:
        """Wall-clock duration, falling back to time-so-far while still running.

        GitLab only writes `duration` once a pipeline finishes, but the elapsed time
        of a running pipeline is the single most useful number on the page.
        """
        if self.duration is not None:
            return self.duration
        if self.started_at is None:
            return None
        end = self.finished_at or datetime.now(timezone.utc)
        return int((end - self.started_at).total_seconds())


@dataclass(frozen=True)
class FailedJob:
    """A job in the pipeline tree that finished in the `failed` state."""

    id: int
    name: str
    stage: str | None
    failure_reason: str
    allow_failure: bool
    pipeline_id: int
    is_trigger_job: bool
    started_at: datetime | None
    finished_at: datetime | None

    @property
    def elapsed_seconds(self) -> int | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class PullRequestPipeline:
    """Everything the status page needs about one PR's pipeline tree."""

    project_path: str
    pr_number: int
    ref: str
    sha: str
    root: Pipeline
    child_pipelines: list[Pipeline]
    job_status_counts: dict[str, int]
    failed_jobs: list[FailedJob]
    failed_jobs_truncated: bool

    @property
    def total_jobs(self) -> int:
        return sum(self.job_status_counts.values())

    @property
    def failed_job_count(self) -> int:
        return sum(
            count for status, count in self.job_status_counts.items() if status in FAILED_STATUSES
        )

    @property
    def in_progress_job_count(self) -> int:
        return sum(
            count
            for status, count in self.job_status_counts.items()
            if status in IN_PROGRESS_STATUSES
        )

    @property
    def is_running(self) -> bool:
        return self.root.status in IN_PROGRESS_STATUSES

    @property
    def blocking_failed_jobs(self) -> list[FailedJob]:
        """Failures that actually fail the pipeline, i.e. excluding allow_failure jobs."""
        return [job for job in self.failed_jobs if not job.allow_failure]

    @property
    def allowed_failed_jobs(self) -> list[FailedJob]:
        return [job for job in self.failed_jobs if job.allow_failure]


def gitlab_ref_pattern(pr_number: int) -> str:
    r"""Build the LIKE pattern matching the GitLab ref for a GitHub PR.

    The gh-gl-sync bridge pushes each PR to GitLab as `pr<number>_<head ref>`
    (see images/gh-gl-sync/SpackCIBridge.py), so we only know the ref's prefix.

    The underscore is escaped because it is a single-character wildcard in LIKE --
    without the escape, `pr12_%` would also match the ref for PR 123.
    """
    return rf"pr{pr_number}\_%"


def gitlab_ref_path_pattern(pr_number: int) -> str:
    """The same pattern as gitlab_ref_pattern, as ci_refs stores it.

    ci_refs holds fully qualified ref paths ("refs/heads/<branch>"), not bare branch
    names.
    """
    return f"refs/heads/{gitlab_ref_pattern(pr_number)}"


def _rows_as_dicts(cursor) -> list[dict]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive timestamp read out of GitLab.

    GitLab's CI timestamps are `timestamp without time zone` holding UTC (Rails'
    default). Reading them through a raw cursor bypasses the ORM's field conversion,
    so they arrive naive -- which would both render wrong under USE_TZ and break any
    arithmetic against an aware `now()`.
    """
    if value is None or value.tzinfo is not None:
        return value

    return value.replace(tzinfo=timezone.utc)


# Project ids never change, so this only needs to be looked up once in a while. The
# TTL is here so that a project created after startup is eventually visible.
@cached(cache=TTLCache(maxsize=32, ttl=60 * 60))
def get_project_id(project_path: str) -> int | None:
    """Resolve a full project path (e.g. "spack/spack-packages") to its numeric id."""
    with connections["gitlab"].cursor() as cursor:
        cursor.execute(PROJECT_ID_QUERY, {"path": project_path})
        row = cursor.fetchone()

    return row[0] if row else None


def get_pull_request_pipeline(project_path: str, pr_number: int) -> PullRequestPipeline | None:
    """Summarise the latest pipeline tree for a GitHub PR, or None if there isn't one.

    Returning None covers both "no such PR" and "the PR has not been mirrored to
    GitLab yet", which are indistinguishable from here and, for the reader, amount
    to the same thing.
    """
    project_id = get_project_id(project_path)
    if project_id is None:
        return None

    with connections["gitlab"].cursor() as cursor:
        root_row = _find_root_pipeline(cursor, project_id, pr_number)
        if root_row is None:
            return None

        cursor.execute(PIPELINE_TREE_QUERY, {"root_id": root_row["id"]})
        tree_rows = _rows_as_dicts(cursor)

        pipeline_ids = [row["id"] for row in tree_rows]
        # A pipeline is always in its own tree, but be defensive: if the recursive
        # query somehow came back empty we still want to report on the parent.
        if root_row["id"] not in pipeline_ids:
            pipeline_ids.append(root_row["id"])
        partition_ids = sorted(
            {row["partition_id"] for row in tree_rows} | {root_row["partition_id"]}
        )
        job_query_params = {
            "pipeline_ids": pipeline_ids,
            "partition_ids": partition_ids,
        }

        cursor.execute(JOB_STATUS_COUNTS_QUERY, job_query_params)
        job_status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute(FAILED_JOBS_QUERY, job_query_params | {"limit": FAILED_JOBS_LIMIT + 1})
        failed_job_rows = _rows_as_dicts(cursor)

    failed_jobs_truncated = len(failed_job_rows) > FAILED_JOBS_LIMIT
    failed_jobs = [
        FailedJob(
            id=row["id"],
            name=row["name"],
            stage=row["stage_name"],
            failure_reason=FAILURE_REASON_MAP.get(row["failure_reason"], "unknown_failure"),
            allow_failure=row["allow_failure"],
            pipeline_id=row["pipeline_id"],
            is_trigger_job=row["type"] == "Ci::Bridge",
            started_at=_as_utc(row["started_at"]),
            finished_at=_as_utc(row["finished_at"]),
        )
        for row in failed_job_rows[:FAILED_JOBS_LIMIT]
    ]

    return PullRequestPipeline(
        project_path=project_path,
        pr_number=pr_number,
        ref=root_row["ref"],
        sha=root_row["sha"],
        root=_pipeline_from_row(root_row),
        child_pipelines=[
            _pipeline_from_row(row) for row in tree_rows if row["id"] != root_row["id"]
        ],
        job_status_counts=job_status_counts,
        failed_jobs=failed_jobs,
        failed_jobs_truncated=failed_jobs_truncated,
    )


def _find_root_pipeline(cursor, project_id: int, pr_number: int) -> dict | None:
    """Find the PR's most recent top-level pipeline.

    Goes through ci_refs first because that is the indexed path (see
    CI_REF_IDS_QUERY), and falls back to filtering on the pipeline's own `ref` for
    pipelines that have no ci_ref.
    """
    cursor.execute(
        CI_REF_IDS_QUERY,
        {
            "project_id": project_id,
            "ref_path_pattern": gitlab_ref_path_pattern(pr_number),
        },
    )
    # Normally one ref, but a PR whose head branch was renamed can leave more than one.
    ci_ref_ids = [row[0] for row in cursor.fetchall()]

    if ci_ref_ids:
        cursor.execute(LATEST_PIPELINE_BY_CI_REF_QUERY, {"ci_ref_ids": ci_ref_ids})
        rows = _rows_as_dicts(cursor)
        if rows:
            return rows[0]

    cursor.execute(
        LATEST_PIPELINE_QUERY,
        {"project_id": project_id, "ref_pattern": gitlab_ref_pattern(pr_number)},
    )
    rows = _rows_as_dicts(cursor)

    return rows[0] if rows else None


def _pipeline_from_row(row: dict) -> Pipeline:
    return Pipeline(
        id=row["id"],
        status=row["status"],
        created_at=_as_utc(row["created_at"]),
        started_at=_as_utc(row["started_at"]),
        finished_at=_as_utc(row["finished_at"]),
        duration=row["duration"],
    )
