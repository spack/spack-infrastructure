CREATE EXTENSION pg_trgm;

-- Jobs Logs Table
CREATE TABLE IF NOT EXISTS job_logs (
    -- Don't make job_id a foreign key, to avoid a situation where the job
    -- is not replicated by DMS into the cloned database in time
    job_id bigint PRIMARY KEY,
    error_taxonomy VARCHAR (256),
    log TEXT,

    -- Retry info
    attempt_number smallint,
    retried boolean,

    -- Whether this job was run on a kubernetes pod or via some other means (a UO runner, for example)
    kubernetes_job boolean,

    -- Status updates over the pod's lifetime
    pod_status JSONB

);
CREATE INDEX job_logs_taxonomy_idx
    on job_logs
    USING btree (error_taxonomy);
CREATE INDEX job_logs_gin_idx
    on job_logs
    USING GIN (log gin_trgm_ops)
;
