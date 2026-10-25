# pratham-2 (Pratham, background agent)

Updated: 14:00 PT

## Doing now
- Nothing. T02, T03 (minimal), T05 done.

## Done
- T02 demo data: `data/` (see data/README.md). Regenerate: `npm run data:build`.
- T03 TS project + SQLite: `package.json`, `tsconfig.json`, `src/db/` (node:sqlite). Load: `npm run db:load`.
- T05 vendor fingerprint: `src/fingerprint/` (see its README). 47 tests pass: `npm test`.
- T05 rhythm + requester confirmation: `profile.rhythm`, 4 rhythm checks, `purchase_orders.requester_*`, demo case IN-SURPRISE-1, `draftRequesterConfirmation()` in src/fingerprint/confirm.ts.
- T05 red-team fixes from pratham-1: combosquat, plural/suffix, freemail + contact-name resolution, wider bank-change wording, no-vendor bank-change finding. Cases in `src/fingerprint/redteam.test.ts`.

## Blocked on
- Qwen language checks need the GB10 model (T01). They are mocked in tests and never run against real vLLM.

## Requests for others
- T01 owner: once vLLM is up, run `LLM_BASE_URL=http://<gb10>:8000/v1 npx tsx -e` with fingerprint() on IN-ATTACK-2 and check the model returns urgency/style_mismatch/unusual_request. Confirm vLLM accepts `chat_template_kwargs` + `response_format: json_object`.
- T04 owner: Findings shape + a suggested hold rule are in docs/ARCHITECTURE.md "Findings format".
- T09 owner: deliver `draftRequesterConfirmation()` drafts to `recipient.contact` (internal only) and record the yes/no reply. Interface in ARCHITECTURE.md "Requester confirmation draft".
- T06 owner: return the same Finding shape with `source: "vision"`. `scanPdf()` in src/fingerprint/pdf.ts already gives PDF text and runs.

## Notes for other agents
- `npm test` runs every `src/**/*.test.ts` with tsx. Node >= 22.13 needed (node:sqlite).
- npm here blocks install scripts by default; esbuild/tsx still work.
- Test DBs: `openDb(":memory:")` + `loadFixtures(db)`.
