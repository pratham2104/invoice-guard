// Lookalike-domain detection. Ideas borrowed from dnstwist's fuzzers (homoglyphs, swaps,
// hyphenation, TLD swaps) and Unicode TR39 confusables, reduced to what a demo needs.

// Common confusables → their Latin lookalike. Cyrillic/Greek letters + digit tricks.
const CONFUSABLES: Record<string, string> = {
  "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
  "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n", "ԛ": "q", "ԝ": "w",
  "α": "a", "ο": "o", "ρ": "p", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "τ": "t",
  "0": "o", "1": "l", "3": "e", "5": "s", "@": "a",
};

/** Map a domain to a "skeleton": confusables folded, multi-char tricks collapsed. */
export function skeleton(domain: string): string {
  let s = domain.toLowerCase().normalize("NFKC");
  s = [...s].map((ch) => CONFUSABLES[ch] ?? ch).join("");
  s = s.replace(/rn/g, "m").replace(/vv/g, "w").replace(/cl/g, "d");
  return s;
}

/** Split "mail.acme-supply.co.uk" → { name: "acme-supply", tld: "co.uk" } (good enough for demo domains). */
export function splitDomain(domain: string): { name: string; tld: string } {
  const parts = domain.toLowerCase().split(".");
  const twoPartTld = parts.length >= 3 && ["co", "com", "org", "net", "ac", "gov", "edu"].includes(parts[parts.length - 2]) && parts[parts.length - 1].length === 2;
  const tldParts = twoPartTld ? 2 : 1;
  return { name: parts[parts.length - 1 - tldParts] ?? "", tld: parts.slice(-tldParts).join(".") };
}

/** Damerau–Levenshtein (optimal string alignment) distance. */
export function editDistance(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

export interface LookalikeResult {
  lookalike: boolean;
  technique?: "homoglyph" | "hyphenation" | "tld-swap" | "typo" | "subdomain" | "plural-or-suffix" | "combosquat";
  distance: number;
}

/** Words scammers bolt onto a real name: acme-supply-billing, acmesupplyinc, acme-supply-ar. */
const SUFFIX_WORDS = ["billing", "payments", "payment", "invoices", "invoice", "pay", "ar", "accounts", "account",
                      "remit", "remittance", "finance", "inc", "llc", "corp", "co", "ltd", "group", "usa", "us", "online", "portal"];

/** Fold plurals per hyphen-token: supplies→supply, boxes→box, tools→tool. */
function singular(token: string): string {
  if (token.length > 4 && token.endsWith("ies")) return token.slice(0, -3) + "y";
  if (token.length > 4 && /(ches|shes|xes|ses|zes)$/.test(token)) return token.slice(0, -2);
  if (token.length > 3 && token.endsWith("s") && !token.endsWith("ss")) return token.slice(0, -1);
  return token;
}

/** Normalised core name: skeleton, suffix words removed (hyphenated or glued on), plurals folded, no hyphens. */
export function coreName(name: string): string {
  let tokens = skeleton(name).split("-").filter(Boolean);
  while (tokens.length > 1 && SUFFIX_WORDS.includes(tokens[tokens.length - 1])) tokens.pop();
  let joined = tokens.map(singular).join("");
  // glued-on suffixes: acmesupplybilling → acmesupply (longest first, keep at least 4 chars)
  for (const w of [...SUFFIX_WORDS].sort((a, b) => b.length - a.length)) {
    if (joined.length - w.length >= 4 && joined.endsWith(w)) { joined = joined.slice(0, -w.length); break; }
  }
  return singular(joined);
}

const GENERIC_WORDS = new Set(["school", "supply", "supplies", "service", "services", "food", "foods", "bus", "lines",
  "it", "the", "and", "of", "company", "inc", "llc", "group", "solutions", "systems", "tech", "office", "products"]);

/** Tokens of a vendor's display name that matter for matching: "Acme School Supply" → [acme, school, supply]. */
function nameTokens(vendorName: string): string[] {
  return vendorName.toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length >= 3).map(singular);
}

/**
 * Is `candidate` pretending to be `trusted`? Exact match (or a subdomain of the real domain) is NOT a lookalike.
 * `vendorName` enables combosquat detection: every token of the name glued into the domain
 * (acmeschoolsupply-billing.com for "Acme School Supply") counts, as long as one token is distinctive.
 */
export function compareDomains(candidate: string, trusted: string, vendorName?: string): LookalikeResult {
  const c = candidate.toLowerCase().trim();
  const t = trusted.toLowerCase().trim();
  if (!c || c === t || c.endsWith("." + t)) return { lookalike: false, distance: 0 };
  const cs = splitDomain(c), ts = splitDomain(t);
  const distance = editDistance(cs.name, ts.name);

  // trusted domain reused inside someone else's domain: acme-supply.com.evil.net
  if (c.startsWith(t + ".") || c.includes("." + ts.name + ".")) return { lookalike: true, technique: "subdomain", distance };
  if (cs.name !== ts.name && skeleton(cs.name) === skeleton(ts.name)) return { lookalike: true, technique: "homoglyph", distance };
  const noHyphen = (s: string) => s.replace(/-/g, "");
  if (cs.name !== ts.name && noHyphen(skeleton(cs.name)) === noHyphen(skeleton(ts.name))) {
    return { lookalike: true, technique: cs.tld === ts.tld ? "hyphenation" : "tld-swap", distance };
  }
  if (cs.name === ts.name && cs.tld !== ts.tld) return { lookalike: true, technique: "tld-swap", distance };

  const cc = coreName(cs.name), tc = coreName(ts.name);
  if (cc === tc) return { lookalike: true, technique: "plural-or-suffix", distance };
  // combosquat: the vendor's whole domain name glued inside a longer name (acmesupplyinvoices, myacme-supply)
  if (tc.length >= 5 && cc.includes(tc)) return { lookalike: true, technique: "combosquat", distance };
  if (vendorName) {
    const toks = nameTokens(vendorName);
    const flat = noHyphen(skeleton(cs.name));
    const distinctive = toks.filter((x) => !GENERIC_WORDS.has(x));
    if (toks.length >= 2 && distinctive.length >= 1 && toks.every((x) => flat.includes(x))) {
      return { lookalike: true, technique: "combosquat", distance };
    }
  }
  // small typo on a name long enough that it's unlikely to be a different company
  const maxLen = Math.max(cs.name.length, ts.name.length);
  if (distance > 0 && distance <= (maxLen >= 8 ? 2 : 1)) return { lookalike: true, technique: "typo", distance };
  if (cc !== cs.name && editDistance(cc, tc) === 1 && tc.length >= 6) return { lookalike: true, technique: "typo", distance };
  return { lookalike: false, distance };
}

export function domainOf(email: string): string {
  return (email.split("@")[1] ?? "").toLowerCase().trim();
}

export function localPartOf(email: string): string {
  return (email.split("@")[0] ?? "").toLowerCase().trim();
}

/** Free webmail: a vendor's AR team writing from one of these is a red flag on its own. */
export const FREEMAIL = new Set(["gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
  "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "zoho.com", "yandex.com"]);
