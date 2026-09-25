#!/bin/sh
set -eu
export PGPASSWORD="$POSTGRES_PASSWORD"
psql -h postgres -U transport -d transport <<'SQL'
CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    sample_id TEXT,
    tr_id TEXT,
    target_stop_id TEXT,
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    prediction_seconds DOUBLE PRECISION NOT NULL,
    model_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT REFERENCES predictions(id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL
