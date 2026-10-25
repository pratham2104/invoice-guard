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
  monthly_max   REAL
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

-- Written only by the rules engine (T04). Released only by a human.
CREATE TABLE IF NOT EXISTS holds (
  id          TEXT PRIMARY KEY,
  invoice_id  TEXT,
  email_id    TEXT,
  vendor_id   TEXT,
  reason      TEXT NOT NULL,
  findings    TEXT NOT NULL,                -- JSON array of Findings
  status      TEXT NOT NULL DEFAULT 'held', -- held | released | rejected
  created_at  TEXT NOT NULL,
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
