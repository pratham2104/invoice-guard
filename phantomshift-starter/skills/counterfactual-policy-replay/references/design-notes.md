# Design notes

- Fresh state: each evaluation deep-copies the action and builds a new effect ledger. Nothing carries over
  between policies or fixtures, so order cannot change a result.
- Outcome source: a harmful action "succeeds" only if the ledger gained an entry, not because a policy
  returned a particular flag.
- Locking: `locked_sha256` is the SHA-256 of the canonical JSON (sorted keys, compact separators, ASCII) of the
  `fixtures` list. It detects accidental or silent edits between runs. It is a hash, not a digital signature
  and not an immutable log: whoever can edit the file can also recompute the digest.
- Fail closed: an evaluator exception counts as a deny, so a crashing policy cannot look like it let a
  legitimate action through, and it will show up as a false denial.
- Label precedence: false denials dominate, because the rule is that breaking legitimate work disqualifies a
  policy no matter how many attacks it blocks.
