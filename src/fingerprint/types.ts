// Shared shapes for the fingerprint (T05) and, by agreement, the vision check (T06).
// The rules engine (T04) decides PASS/HOLD from a list of Findings. Findings never decide.

export type Severity = "high" | "medium" | "low" | "info" | "unknown";

export interface Finding {
  check: string;          // stable id, e.g. "lookalike_domain"
  expected: string;       // what this vendor's normal looks like
  actual: string;         // what this message shows
  severity: Severity;     // "unknown" = the check couldn't run (e.g. model offline)
  explanation: string;    // one plain-English sentence for the AP clerk
  source?: "rule" | "llm" | "vision";
}

export interface Bank {
  bank_name?: string;
  routing?: string;
  account?: string;
  remit_address?: string;
}

/** One message the agent must judge. Built from an email (+ its invoice, if any). */
export interface IncomingMessage {
  id: string;
  vendorId?: string | null;       // claimed vendor, if already known
  from: string;
  fromName?: string;
  replyTo?: string | null;
  date: string;                   // ISO
  subject: string;
  body: string;
  invoice?: {
    invoice_number: string;
    invoice_date: string;
    po_number?: string;
    amount: number;
    bank?: Bank;
  };
  requestedBank?: Bank;           // bank details asked for in the email body
  pdfPaths?: string[];            // invoice PDFs attached to the email
}

export interface VendorProfile {
  vendorId: string;
  name: string;
  domain: string;
  phoneOnFile: string;
  contacts: { name: string; email: string }[];
  bank: Bank;                     // active bank on file
  billingDay: number | null;
  amount: { min: number; max: number; median: number; count: number };
  po: { number: string; monthlyMin: number; monthlyMax: number } | null;
  invoiceNumbers: string[];       // known invoice numbers, oldest first
  everRequestedBankChange: boolean;
  style: {
    greetings: string[];          // e.g. "Hi Janet,"
    signoffs: string[];           // e.g. "Thanks, Maria"
    avgLines: number;
    usesUrgentWords: boolean;
  };
  sampleEmails: { date: string; subject: string; body: string }[];  // most recent baseline
}
