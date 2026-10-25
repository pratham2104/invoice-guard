// The dashboard's view of the API (src/api/, T03b). Kept in step with the contract in the brief.
// Finding mirrors src/fingerprint/types.ts; it is redeclared here so web/ builds on its own.

export type Severity = "high" | "medium" | "low" | "info" | "unknown";
export type Outcome = "HOLD_FRAUD_RISK" | "HOLD_CONFIRM" | "PASS";
export type CaseState =
  | "OPEN"
  | "AWAITING_VENDOR"
  | "AWAITING_REQUESTER"
  | "READY_FOR_APPROVAL"
  | "APPROVED"
  | "REJECTED";

export interface Finding {
  check: string;
  expected: string;
  actual: string;
  severity: Severity;
  explanation: string;
  source?: "rule" | "llm" | "vision";
  action?: "confirm_with_requester" | "callback_vendor";
}

export interface Status {
  product: string;
  org: string;
  model: { endpoint: string; id: string; up: boolean };
  mode: "model" | "rules-only";
  cloudCalls: number;
  inbox: { watching: boolean; dir: string };
  sandbox: { name: string; egress: string };
  counts: {
    heldAmount: number;
    held: number;
    checkedToday: number;
    cleared: number;
    awaitingVendor: number;
    awaitingRequester: number;
  };
}

export interface CaseSummary {
  id: string;
  vendorId: string | null;
  vendorName: string | null;
  invoiceNumber: string | null;
  amount: number | null;
  outcome: Outcome;
  nextStep: "none" | "phone_callback" | "requester_confirmation";
  state: CaseState;
  status: string;
  severity: Severity;
  score: number;
  reason: string;
  createdAt: string;
  topChecks: string[];
}

export interface InvoiceLine {
  lineNo: number;
  description: string;
  qty: number;
  unitPrice: number;
  amount: number;
}

export interface InvoiceView {
  invoiceNumber: string;
  invoiceDate: string;
  poNumber: string | null;
  amount: number;
  bankName: string | null;
  routingLast4: string | null;
  accountLast4: string | null;
  remitAddress: string | null;
  lines: InvoiceLine[];
  pdfUrl: string | null;
}

export interface Callback {
  id: string;
  phone: string;
  script: string;
  status: "open" | "confirmed_fraud" | "confirmed_legit" | "no_answer";
  outcome: string | null;
  createdAt: string;
  completedAt: string | null;
  /** Recording of the voice agent's call, when the API has one. */
  recordingUrl?: string | null;
  /** Transcript JSON for that recording ({ duration, turns, result }). */
  transcriptUrl?: string | null;
}

/** The call Halberd's local voice agent placed: an audio file and its transcript JSON. */
export interface CallRef { audio: string; transcript: string | null }

export interface CallTranscript {
  duration: number;
  turns: { speaker: "agent" | "vendor"; name: string; start: number; end: number; text: string }[];
  result: string;
}

export interface RequesterCheck {
  id: string;
  recipientName: string | null;
  recipientContact: string | null;
  recipientDepartment: string | null;
  text: string;
  source: "llm" | "template";
  status: "open" | "confirmed" | "denied";
  reply: string | null;
  createdAt: string;
}

export interface AuditEvent {
  id: number | string;
  ts: string;
  actor: string;
  action: string;
  detail: unknown;
}

export interface CaseDetail {
  case: CaseSummary;
  vendor: {
    id: string;
    name: string;
    domain: string;
    phoneOnFile: string;
    address: string;
    contacts: { name: string; email: string; role?: string }[];
  } | null;
  bankOnFile: {
    bankName: string;
    routingLast4: string;
    accountLast4: string;
    remitAddress: string;
    verifiedAt: string | null;
  } | null;
  invoice: { current: InvoiceView | null; lastReal: InvoiceView | null };
  email: {
    from: string;
    fromName: string | null;
    replyTo: string | null;
    to: string;
    subject: string;
    date: string;
    bodyExcerpt: string;
  } | null;
  findings: Finding[];
  decision: { outcome: Outcome; nextStep: string; score: number; severity: Severity; reasons: string[] };
  callbacks: Callback[];
  requesterChecks: RequesterCheck[];
  audit: { events: AuditEvent[]; chainOk: boolean; count: number };
  /** Demo label for the held invoice, e.g. "Near-copy address", with a one-line subline. Mock only for now. */
  scenario?: { label: string; subline: string } | null;
  /** Optional plain sentence for "Why Halberd held it"; otherwise derived from the findings. */
  why?: string | null;
  /** Text a person can't see in the invoice PDF, if any. */
  hiddenText?: string | null;
  /** The voice agent's call for this case, if there is a recording. */
  call?: CallRef | null;
}

export interface AlertItem {
  id: number | string;
  ts: string;
  caseId: string;
  text: string;
  channel: string;
  sent: boolean;
}

export type CallbackResult = "confirmed_fraud" | "confirmed_legit" | "no_answer";
export type Role = "manager" | "clerk";

export interface DemoFile {
  file: string;
  label?: string;
  processed?: boolean;
}

// ------------------------------------------------------------------ v2: invoices list (GET /api/invoices)
export type Risk = "fraud" | "confirm" | "cleared";

export interface InvoiceRow {
  id: string;
  kind: "case" | "invoice";
  caseId: string | null;
  vendorName: string | null;
  invoiceNumber: string | null;
  date: string;
  amount: number | null;
  risk: Risk;
  state: string;
}

export interface ClearedInvoice {
  kind: "invoice";
  invoice: InvoiceView & { id: string; status?: string };
  vendor: { id: string; name: string; domain?: string; phoneOnFile?: string } | null;
  verdict: string | null;
}

export type InvoiceDetail = ({ kind: "case" } & CaseDetail) | ClearedInvoice;
