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
  technique?: "homoglyph" | "hyphenation" | "tld-swap" | "typo" | "subdomain";
  distance: number;
}

/** Is `candidate` pretending to be `trusted`? Exact match is NOT a lookalike. */
export function compareDomains(candidate: string, trusted: string): LookalikeResult {
  const c = candidate.toLowerCase().trim();
  const t = trusted.toLowerCase().trim();
  if (c === t) return { lookalike: false, distance: 0 };
  const cs = splitDomain(c), ts = splitDomain(t);
  const distance = editDistance(cs.name, ts.name);

  // trusted name used as a subdomain of something else: acme-supply.com.evil.net
  if (c.startsWith(t + ".") || c.includes("." + ts.name + ".")) return { lookalike: true, technique: "subdomain", distance };
  if (cs.name !== ts.name && skeleton(cs.name) === skeleton(ts.name)) return { lookalike: true, technique: "homoglyph", distance };
  const noHyphen = (s: string) => s.replace(/-/g, "");
  if (cs.name !== ts.name && noHyphen(skeleton(cs.name)) === noHyphen(skeleton(ts.name))) {
    return { lookalike: true, technique: cs.tld === ts.tld ? "hyphenation" : "tld-swap", distance };
  }
  if (cs.name === ts.name && cs.tld !== ts.tld) return { lookalike: true, technique: "tld-swap", distance };
  // small typo on a name long enough that it's unlikely to be a different company
  const maxLen = Math.max(cs.name.length, ts.name.length);
  if (distance > 0 && distance <= (maxLen >= 8 ? 2 : 1)) return { lookalike: true, technique: "typo", distance };
  return { lookalike: false, distance };
}

export function domainOf(email: string): string {
  return (email.split("@")[1] ?? "").toLowerCase().trim();
}
