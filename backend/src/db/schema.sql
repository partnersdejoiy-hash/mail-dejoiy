-- Dejoiy Mail — Phase 1 MVP schema
-- Multi-tenant: EVERY table carries org_id. No cross-org queries, ever.
-- Conventions: UUID primary keys generated in application code (no pg extensions
-- required). Timestamps: timestamptz. Emails stored lower-cased by the app.

CREATE TABLE IF NOT EXISTS orgs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    plan        TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free','starter','business','enterprise')),
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plans (
    id               TEXT PRIMARY KEY,
    code             TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    price_inr_monthly INTEGER NOT NULL CHECK (price_inr_monthly >= 0),
    max_users        INTEGER NOT NULL CHECK (max_users > 0),
    storage_gb       INTEGER NOT NULL DEFAULT 5,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS domains (
    id                 TEXT PRIMARY KEY,
    org_id             TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    domain             TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (verification_status IN ('pending','verified','failed')),
    verification_code  TEXT NOT NULL,
    dkim_selector      TEXT NOT NULL DEFAULT 'dmail',
    dkim_public_key    TEXT,
    dkim_private_key_enc TEXT,          -- encrypted at rest (KMS in production)
    mx_ok              BOOLEAN NOT NULL DEFAULT FALSE,
    spf_ok             BOOLEAN NOT NULL DEFAULT FALSE,
    dkim_ok            BOOLEAN NOT NULL DEFAULT FALSE,
    dmarc_ok           BOOLEAN NOT NULL DEFAULT FALSE,
    last_checked_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, domain)
);

CREATE TABLE IF NOT EXISTS users (
    id             TEXT PRIMARY KEY,
    org_id         TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    email          TEXT NOT NULL,                       -- lower-cased by app
    password_hash  TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'user'
        CHECK (role IN ('super_admin','admin','user')),
    status         TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','suspended','invited')),
    totp_secret_enc TEXT,                               -- encrypted at rest
    totp_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);

CREATE TABLE IF NOT EXISTS mailboxes (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    domain_id   TEXT NOT NULL REFERENCES domains(id) ON DELETE RESTRICT,
    local_part  TEXT NOT NULL,
    quota_bytes BIGINT NOT NULL DEFAULT 5368709120,    -- 5 GB default
    used_bytes  BIGINT NOT NULL DEFAULT 0,
    vacation_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    vacation_subject TEXT,
    vacation_body    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_id, local_part)
);

CREATE TABLE IF NOT EXISTS folders (
    id         TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    mailbox_id TEXT NOT NULL REFERENCES mailboxes(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'custom'
        CHECK (kind IN ('inbox','sent','drafts','trash','spam','custom')),
    parent_id  TEXT REFERENCES folders(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (mailbox_id, name)
);
CREATE INDEX IF NOT EXISTS idx_folders_mailbox ON folders(mailbox_id);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    mailbox_id      TEXT NOT NULL REFERENCES mailboxes(id) ON DELETE CASCADE,
    folder_id       TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    message_id_hdr  TEXT,
    thread_id       TEXT,
    from_addr       TEXT NOT NULL,
    to_addrs        JSONB NOT NULL DEFAULT '[]',
    cc_addrs        JSONB NOT NULL DEFAULT '[]',
    bcc_addrs       JSONB NOT NULL DEFAULT '[]',
    subject         TEXT NOT NULL DEFAULT '',
    snippet         TEXT NOT NULL DEFAULT '',
    body_text       TEXT NOT NULL DEFAULT '',
    body_html       TEXT NOT NULL DEFAULT '',
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    is_starred      BOOLEAN NOT NULL DEFAULT FALSE,
    has_attachments BOOLEAN NOT NULL DEFAULT FALSE,
    internal_date   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_mailbox_folder_date
    ON messages(mailbox_id, folder_id, internal_date DESC);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

CREATE TABLE IF NOT EXISTS attachments (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    message_id   TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    storage_key  TEXT NOT NULL,   -- local path in MVP; S3 key in production
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);

CREATE TABLE IF NOT EXISTS filters (
    id         TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    mailbox_id TEXT NOT NULL REFERENCES mailboxes(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    conditions JSONB NOT NULL DEFAULT '[]',  -- [{field, op, value}]
    actions    JSONB NOT NULL DEFAULT '[]',  -- [{type: move|label|mark_read, ...}]
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_filters_mailbox ON filters(mailbox_id);

-- Server-side sessions. Only the SHA-256 of the token is stored.
CREATE TABLE IF NOT EXISTS api_sessions (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    ip          TEXT,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON api_sessions(user_id);

-- Billing-ready tables. Razorpay ids are filled by the billing service (STUB in MVP).
CREATE TABLE IF NOT EXISTS subscriptions (
    id                      TEXT PRIMARY KEY,
    org_id                  TEXT NOT NULL UNIQUE REFERENCES orgs(id) ON DELETE CASCADE,
    plan_id                 TEXT NOT NULL REFERENCES plans(id),
    status                  TEXT NOT NULL DEFAULT 'trialing'
        CHECK (status IN ('trialing','active','past_due','canceled')),
    razorpay_subscription_id TEXT,       -- STUB: set when Razorpay is wired
    razorpay_customer_id     TEXT,       -- STUB
    seats                   INTEGER NOT NULL DEFAULT 1,
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seat_events (
    id         TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    user_id    TEXT REFERENCES users(id) ON DELETE SET NULL,
    event      TEXT NOT NULL CHECK (event IN ('seat_added','seat_removed')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_seat_events_org ON seat_events(org_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    actor_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    action        TEXT NOT NULL,
    target_type   TEXT,
    target_id     TEXT,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_org_time ON audit_log(org_id, created_at DESC);

-- Outbound mail queue. MVP: processed by the mailer stub; production: worker -> Postfix/SES.
CREATE TABLE IF NOT EXISTS outbox (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    mailbox_id   TEXT NOT NULL REFERENCES mailboxes(id) ON DELETE CASCADE,
    message_id   TEXT REFERENCES messages(id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','sending','sent','failed')),
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, created_at);
