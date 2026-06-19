CREATE TABLE IF NOT EXISTS quota_configs (
    org_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    monthly_limit BIGINT NOT NULL CHECK (monthly_limit >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, feature)
);

CREATE TABLE IF NOT EXISTS monthly_usage (
    org_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    period TEXT NOT NULL,
    limit_units BIGINT NOT NULL CHECK (limit_units >= 0),
    used_units BIGINT NOT NULL DEFAULT 0 CHECK (used_units >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, feature, period)
);

INSERT INTO quota_configs (org_id, feature, monthly_limit)
VALUES
    ('org_123', 'container_tracking', 500),
    ('org_123', 'sailing_schedule', 1000),
    ('org_999', 'container_tracking', 300)
ON CONFLICT (org_id, feature) DO NOTHING;
