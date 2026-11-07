-- PostgreSQL incremental review DDL, generated from Alembic 20261108_rule_tasks.
-- Connect to devdb; prerequisite: crosstax.rule_versions and previous migrations exist.
-- Preferred deployment: uv run alembic upgrade head.
-- Do not execute this SQL in addition to that migration: both create the same tables.
-- Manual execution does not update alembic_version; reconcile migration history before later upgrades.
-- No runtime code executes this PostgreSQL-specific review artifact.
BEGIN;

CREATE TABLE crosstax.rule_task_queue_state (
    id SERIAL NOT NULL,
    generation INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_rule_queue_singleton CHECK (id = 1)
);

CREATE TABLE crosstax.rule_validation_tasks (
    task_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_digest VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    rule_version_id VARCHAR(64) NOT NULL,
    rule_revision INTEGER NOT NULL,
    engine_build_id VARCHAR(64) NOT NULL,
    payload_ciphertext TEXT,
    result_ciphertext TEXT,
    error_code VARCHAR(64),
    attempts INTEGER NOT NULL,
    claim_token VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    deadline_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    lease_until TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (task_id),
    CONSTRAINT ck_rule_task_status CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
    CONSTRAINT ck_rule_task_attempts CHECK (attempts >= 0),
    FOREIGN KEY(rule_version_id) REFERENCES crosstax.rule_versions (version_id) ON DELETE RESTRICT,
    UNIQUE (idempotency_key)
);

CREATE INDEX ix_rule_task_claim ON crosstax.rule_validation_tasks (status, lease_until, created_at);

CREATE INDEX ix_rule_task_expiry ON crosstax.rule_validation_tasks (expires_at);

CREATE INDEX ix_rule_task_session ON crosstax.rule_validation_tasks (session_id, created_at);


COMMIT;
