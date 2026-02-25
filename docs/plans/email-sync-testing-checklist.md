# Email Sync — Testing Checklist

Generated from audit of `scripts/imap_sync.py`.

## Bugs fixed (2026-02-23)

- [x] Gmail label with spaces not quoted for IMAP SELECT → `_quote_folder()` added
- [x] `_quote_folder` didn't escape internal double-quotes → RFC 3501 escaping added
- [x] `signal is None` in `_scan_unmatched_leads` allowed classifier failures through → now skips
- [x] Email with no Message-ID re-inserted on every sync → `_parse_message` returns `None` when ID missing
- [x] `todo_attached` missing from early-return dict in `sync_all` → added
- [x] Body phrase check truncated at 800 chars (rejection footers missed) → bumped to 1500
- [x] `_DONT_FORGET_VARIANTS` missing left single quotation mark `\u2018` → added

---

## Unit tests — phrase filter

- [ ] `_has_rejection_or_ats_signal` — rejection phrase at char 1501 (boundary)
- [ ] `_has_rejection_or_ats_signal` — right single quote `\u2019` in "don't forget"
- [ ] `_has_rejection_or_ats_signal` — left single quote `\u2018` in "don't forget"
- [ ] `_has_rejection_or_ats_signal` — ATS subject phrase only checked against subject, not body
- [ ] `_has_rejection_or_ats_signal` — spam subject prefix `@` match
- [ ] `_has_rejection_or_ats_signal` — `"UNFORTUNATELY"` (uppercase → lowercased correctly)
- [ ] `_has_rejection_or_ats_signal` — phrase in body quoted thread (beyond 1500 chars) is not blocked

## Unit tests — folder quoting

- [ ] `_quote_folder("TO DO JOBS")` → `'"TO DO JOBS"'`
- [ ] `_quote_folder("INBOX")` → `"INBOX"` (no spaces, no quotes added)
- [ ] `_quote_folder('My "Jobs"')` → `'"My \\"Jobs\\""'`
- [ ] `_search_folder` — folder doesn't exist → returns `[]`, no exception
- [ ] `_search_folder` — special folder `"[Gmail]/All Mail"` (brackets + slash)

## Unit tests — message-ID dedup

- [ ] `_get_existing_message_ids` — NULL message_id in DB excluded from set
- [ ] `_get_existing_message_ids` — empty string `""` excluded from set
- [ ] `_get_existing_message_ids` — job with no contacts returns empty set
- [ ] `_parse_message` — email with no Message-ID header returns `None`
- [ ] `_parse_message` — email with RFC2047-encoded subject decodes correctly
- [ ] No email is inserted twice across two sync runs (integration)

## Unit tests — classifier & signal

- [ ] `classify_stage_signal` — returns one of 5 labels or `None`
- [ ] `classify_stage_signal` — returns `None` on LLM error
- [ ] `classify_stage_signal` — returns `"neutral"` when no label matched in LLM output
- [ ] `classify_stage_signal` — strips `<think>…</think>` blocks
- [ ] `_scan_unmatched_leads` — skips when `signal is None`
- [ ] `_scan_unmatched_leads` — skips when `signal == "rejected"`
- [ ] `_scan_unmatched_leads` — proceeds when `signal == "neutral"`
- [ ] `extract_lead_info` — returns `(None, None)` on bad JSON
- [ ] `extract_lead_info` — returns `(None, None)` on LLM error

## Integration tests — TODO label scan

- [ ] `_scan_todo_label` — `todo_label` empty string → returns 0
- [ ] `_scan_todo_label` — `todo_label` missing from config → returns 0
- [ ] `_scan_todo_label` — folder doesn't exist on IMAP server → returns 0, no crash
- [ ] `_scan_todo_label` — email matches company + action keyword → contact attached
- [ ] `_scan_todo_label` — email matches company but no action keyword → skipped
- [ ] `_scan_todo_label` — email matches no company term → skipped
- [ ] `_scan_todo_label` — duplicate message-ID → not re-inserted
- [ ] `_scan_todo_label` — stage_signal set when classifier returns non-neutral
- [ ] `_scan_todo_label` — body fallback (company only in body[:300]) → still matches
- [ ] `_scan_todo_label` — email handled by `sync_job_emails` first not re-added by label scan

## Integration tests — unmatched leads

- [ ] `_scan_unmatched_leads` — genuine lead inserted with synthetic URL `email://domain/hash`
- [ ] `_scan_unmatched_leads` — same email not re-inserted on second sync run
- [ ] `_scan_unmatched_leads` — duplicate synthetic URL skipped
- [ ] `_scan_unmatched_leads` — `extract_lead_info` returns `(None, None)` → no insertion
- [ ] `_scan_unmatched_leads` — rejection phrase in body → blocked before LLM
- [ ] `_scan_unmatched_leads` — rejection phrase in quoted thread > 1500 chars → passes filter (acceptable)

## Integration tests — full sync

- [ ] `sync_all` with no active jobs → returns dict with all 6 keys incl. `todo_attached: 0`
- [ ] `sync_all` return dict shape identical on all code paths
- [ ] `sync_all` with `job_ids` filter → only syncs those jobs
- [ ] `sync_all` `dry_run=True` → no DB writes
- [ ] `sync_all` `on_stage` callback fires: "connecting", "job N/M", "scanning todo label", "scanning leads"
- [ ] `sync_all` IMAP connection error → caught, returned in `errors` list
- [ ] `sync_all` per-job exception → other jobs still sync

## Config / UI

- [ ] Settings UI field for `todo_label` (currently YAML-only)
- [ ] Warn in sync summary when `todo_label` folder not found on server
- [ ] Clear error message when `config/email.yaml` is missing
- [ ] `test_email_classify.py --verbose` shows correct blocking phrase for each BLOCK

## Backlog — Known issues

- [ ] **The Ladders emails confuse the classifier** — promotional/job alert emails from `@theladders.com` are matching the recruitment keyword filter and being treated as leads. Fix: add a sender-based skip rule in `_scan_unmatched_leads` for known job board senders (similar to how LinkedIn Alert emails are short-circuited before the LLM classifier). Senders to exclude: `@theladders.com`, and audit for others (Glassdoor alerts, Indeed digest, ZipRecruiter, etc.).

---

## Performance & edge cases

- [ ] Email with 10 000-char body → truncated to 4000 chars, no crash
- [ ] Email with binary attachment → `_parse_message` returns valid dict, no crash
- [ ] Email with multiple `text/plain` MIME parts → first part taken
- [ ] `get_all_message_ids` with 100 000 rows → completes in < 1s
