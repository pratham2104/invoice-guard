# Receipt format

```
receipt_version        "agent-incident-receipt/1"
incident_id            string
redaction              {applied, emails_redacted, redactions_by_kind, total}
sections               {observations, policy_diff, approval, test_results}   (all redacted)
section_digests        {section: sha256(canonical(section))}
digest                 sha256(canonical({receipt_version, incident_id, redaction, section_digests}))
hash_algorithm         "sha256"
canonicalization       "json:sort_keys,compact_separators,ascii,no_nan"
provenance_label, notice
```

`verify` recomputes `section_digests` from `sections` and `digest` from the preimage above, then compares both
with the claimed values. Fields outside the preimage (`notice`, `provenance_label`, `canonicalization`,
`hash_algorithm`) are informational and are not protected by the digest.

A hash is NOT a digital signature and NOT an immutable log. Anyone who can edit a receipt can recompute its digest.
