-- Invoice Guard SQLite schema. Money in dollars as REAL (demo scale), dates as ISO strings.

CREATE TABLE IF NOT EXISTS vendors (
  id            TEXT PRIMARY KEY,           -- V001
  name          TEXT NOT NULL,
  domain        TEXT NOT NULL,              -- acme-supply.com
  address       TEXT,
  phone_on_file TEXT NOT NULL,              -- the ONLY number used for callbacks
  billing_day   INTEGER,                    -- day of month the vendor normally bills
  terms         TEXT,
  invoice_prefix TEXT
);

CREATE TABLE IF NOT EXISTS vendor_contacts (
  vendor_id TEXT NOT NULL REFERENCES vendors(id),
  name      TEXT NOT NULL,
  email     TEXT NOT NULL,
  role      TEXT,
  PRIMARY KEY (vendor_id, email)
);

-- Trusted bank on file. One active row per vendor; changes only via a human-verified callback.
CREATE TABLE IF NOT EXISTS vendor_banks (
  vendor_id     TEXT NOT NULL REFERENCES vendors(id),
  bank_name     TEXT NOT NULL,
  routing       TEXT NOT NULL,
  account       TEXT NOT NULL,
  remit_address TEXT,
  active        INTEGER NOT NULL DEFAULT 1,
  verified_at   TEXT,
  verified_by   TEXT
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  number        TEXT PRIMARY KEY,           -- PO-2026-0117
  vendor_id     TEXT NOT NULL REFERENCES vendors(id),
  description   TEXT,
  annual_limit  REAL,
  monthly_min   REAL,
  monthly_max   REAL,
  requester_name       TEXT,              -- district staff who ordered: confirm surprise bills with them
  requester_contact    TEXT,              -- internal email / Slack handle, never the vendor
  requester_department TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  id             TEXT PRIMARY KEY,          -- INV-ACME-1051
  vendor_id      TEXT NOT NULL REFERENCES vendors(id),
  invoice_number TEXT NOT NULL,
  invoice_date   TEXT NOT NULL,
  po_number      TEXT,
  amount         REAL NOT NULL,
  bank_name      TEXT,
  routing        TEXT,
  account        TEXT,
  remit_address  TEXT,
  status         TEXT NOT NULL,             -- received | approved | paid | held | rejected
  source_email_id TEXT
);

CREATE TABLE IF NOT EXISTS invoice_lines (
  invoice_id  TEXT NOT NULL REFERENCES invoices(id),
  line_no     INTEGER NOT NULL,
  description TEXT,
  qty         REAL,
  unit_price  REAL,
  amount      REAL,
  PRIMARY KEY (invoice_id, line_no)
);

CREATE TABLE IF NOT EXISTS payments (
  id         TEXT PRIMARY KEY,
  invoice_id TEXT NOT NULL REFERENCES invoices(id),
  vendor_id  TEXT NOT NULL REFERENCES vendors(id),
  amount     REAL NOT NULL,
  paid_on    TEXT NOT NULL,
  routing    TEXT,
  account    TEXT,
  method     TEXT
);

-- Every email the AP inbox has seen: history (baseline) and incoming (to judge).
CREATE TABLE IF NOT EXISTS emails (
  id          TEXT PRIMARY KEY,
  vendor_id   TEXT REFERENCES vendors(id),  -- claimed vendor (may be an impersonation)
  from_addr   TEXT NOT NULL,
  from_name   TEXT,
  reply_to    TEXT,
  to_addr     TEXT,
  date        TEXT NOT NULL,
  subject     TEXT,
  body        TEXT,
  attachments TEXT,                         -- JSON array of filenames
  kind        TEXT NOT NULL,                -- history | incoming
  scenario    TEXT
);

-- One row per case (T15). Opened by the agent when rules say HOLD; only humans move it forward.
CREATE TABLE IF NOT EXISTS holds (
  id          TEXT PRIMARY KEY,             -- HOLD-0001
  invoice_id  TEXT,                         -- invoice number, if known
  email_id    TEXT,                         -- Message-ID of the email that triggered it
  vendor_id   TEXT,                         -- null = sender not in the vendor master
  reason      TEXT NOT NULL,                -- decision reason (plain sentence)
  findings    TEXT NOT NULL,                -- JSON array of Findings, long numbers masked
  status      TEXT NOT NULL DEFAULT 'held', -- held | released | rejected
  outcome     TEXT,                         -- HOLD_FRAUD_RISK | HOLD_CONFIRM
  next_step   TEXT,                         -- phone_callback | requester_confirmation
  state       TEXT NOT NULL DEFAULT 'OPEN', -- OPEN | AWAITING_VENDOR | AWAITING_REQUESTER | READY_FOR_APPROVAL | APPROVED | REJECTED
  severity    TEXT,
  score       INTEGER,
  source_file TEXT,
  verification_started_by TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT,
  resolved_at TEXT,
  resolved_by TEXT                          -- a human's name, never the agent
);

CREATE TABLE IF NOT EXISTS callbacks (
  id          TEXT PRIMARY KEY,
  hold_id     TEXT NOT NULL REFERENCES holds(id),
  vendor_id   TEXT NOT NULL REFERENCES vendors(id),
  phone       TEXT NOT NULL,                -- copied from vendors.phone_on_file
  script      TEXT,
  status      TEXT NOT NULL DEFAULT 'open', -- open | confirmed_fraud | confirmed_legit | no_answer
  outcome     TEXT,
  created_at  TEXT NOT NULL,
  completed_at TEXT
);

-- "Did you order this?" checks sent to the internal PO requester (HOLD_CONFIRM). Never the vendor.
CREATE TABLE IF NOT EXISTS requester_checks (
  id           TEXT PRIMARY KEY,
  hold_id      TEXT NOT NULL REFERENCES holds(id),
  recipient_name    TEXT,
  recipient_contact TEXT,                   -- internal staff contact; null = route to the AP lead
  recipient_department TEXT,
  text         TEXT NOT NULL,
  source       TEXT NOT NULL,               -- llm | template
  status       TEXT NOT NULL DEFAULT 'open', -- open | confirmed | denied
  reply        TEXT,
  created_at   TEXT NOT NULL,
  completed_at TEXT
);

-- Tamper-evident audit log (port of prerna-1's case_events): each row hashes the previous one.
CREATE TABLE IF NOT EXISTS audit_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id     TEXT NOT NULL,
  ts          TEXT NOT NULL,
  actor       TEXT NOT NULL,                -- "agent" or a human user
  action      TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  prev_hash   TEXT NOT NULL,
  hash        TEXT NOT NULL
);

-- Idempotency: each email is processed once.
CREATE TABLE IF NOT EXISTS processed_messages (
  message_id   TEXT PRIMARY KEY,
  file         TEXT,
  processed_at TEXT NOT NULL,
  outcome      TEXT NOT NULL,
  case_id      TEXT
);

-- In-app alert feed (T09). Same DDL as src/alerts ensureAlertsTable().
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  vendor_name TEXT,
  outcome TEXT NOT NULL,
  state TEXT,
  headline TEXT NOT NULL,
  reason TEXT NOT NULL,
  slack_sent INTEGER NOT NULL DEFAULT 0,
  slack_note TEXT
);
