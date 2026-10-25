# Finding codes

| Code | Severity | Meaning |
|---|---|---|
| MALFORMED_CALL | deny | Call is not an object with string `tool` and object `args` (string keys). |
| TOOLS_INVALID | deny | The supplied tool registry is malformed. |
| UNKNOWN_TOOL | deny | Tool name (after NFKC and trim) is not in the registry. |
| EXTRA_ARG | deny | Argument not defined for the tool. |
| MISSING_ARG | deny | Required argument absent. Never filled in or guessed. |
| WRONG_TYPE | deny | Argument type differs from the schema (bool is not integer). |
| DUPLICATE_ARG | deny | Two argument names collide after normalisation. |
| DESTINATION_OUT_OF_SCOPE | deny | Email or URL not in the trusted scope values or domains. |
| DESTINATION_MALFORMED | deny | Ambiguous destination (several recipients, userinfo, odd scheme, control characters). |
| RECIPIENT_OUT_OF_SCOPE | deny | Recipient (for example a payee account) not in the trusted scope. |
| RESOURCE_OUT_OF_SCOPE | deny | Resource (for example a file path) not in the trusted scope. |
| AMOUNT_OUT_OF_SCOPE | deny | Amount not a positive integer within the trusted cap, or no cap in scope. |
| SENSITIVE_WITHOUT_TRUSTED_SCOPE | hold | Sensitive tool not granted by a trusted scope (or no scope given). |
| NO_TRUSTED_SCOPE | hold | Non-sensitive tool has scoped arguments but no usable scope was given. |
| SCOPE_INVALID | hold | The scope record is malformed and was ignored. |
| AUTHORITY_CLAIM_IN_UNTRUSTED_TEXT | hold | A text-role argument contains an authority claim (`field` names it, `detail` is the pattern). |
| AUTHORITY_FIELD_IGNORED | hold | The call carries a field named like an authority grant (approved, scope, override ...). Ignored. |
| TOOL_NAME_NOT_CANONICAL | hold | Tool name only matched after NFKC or trim. |
| HIDDEN_CHARACTERS | hold | Control or format (zero-width) characters in a name or value. |
| PROVENANCE_MALFORMED | hold | Claimed provenance is not a map of strings. Treated as untrusted. |
| UNEXPECTED_CALL_FIELD | info | Unknown top-level field with a neutral name. Ignored. |
| AUTHORITY_CLAIM_IN_DOCUMENT | info | Document text contains an authority claim. Recorded only. |
| CLAIMED_UNTRUSTED_SOURCE | info | Agent claims a scoped argument did not come from user or registry. Recorded only. |

Authority patterns: `claims_approval`, `claims_admin_override`, `claims_ignore_previous`,
`claims_system_note`, `claims_authorization`.
