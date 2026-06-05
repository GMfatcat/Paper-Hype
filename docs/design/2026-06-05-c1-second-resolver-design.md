# C1 second resolver (OpenAlex) — design spec (2026-06-05)

## Goal

Reduce C1 reference false-positives by adding a **second resolution source**:
when Crossref `query.bibliographic` fails to match a reference, retry against
**OpenAlex search-by-title** before declaring the reference unresolved — without
hurting the calibrated C1 recall (~0.82 on fabricated fakes).

## Why (measured + spiked)

- The 20-paper Mode C C1 test showed legit papers running 12–55% references
  unresolved (BitNet 0.50, LoRA 0.55) — false positives.
- Round ② (reference cleaning) proved the citation-key noise was NOT the cause;
  the FP driver is Crossref's single ranking missing real references.
- Spike: feeding the Crossref-missed real references to OpenAlex
  `/works?search=<ref>` resolved 3 of 4 (BoolQ, "What Can ResNet Learn…",
  "A Practical Guide to Splines"); the 4th (OPTQ) correctly stayed unmatched
  because `match_any` rejects OpenAlex's wrong top-1. So OpenAlex is a genuine
  second lever.
- Semantic Scholar's unauthenticated API returns HTTP 429 on every call →
  unusable for batch reference resolution. OpenAlex (already used here, with a
  `mailto`) is the reliable choice.

## Scope

- **In:** a new injectable fetcher `_search_reference_openalex(ref)`; extend
  `resolve_refs` with a third resolution step (OpenAlex, only on Crossref miss);
  tests; re-measurement of recall (hard) and the live subset; live sync.
- **Out:** Semantic Scholar (429). Paper-level second resolution for too-new
  papers (the (a) variant) — deferred; GRAY is already handled as honest manual
  fallback, not a false signal.
- **Out:** loosening `match_any` or moving off top-1 — round ② / the earlier C1
  calibration showed that trades recall. The second source is also top-1 + strict
  `match_any`.

## Architecture

`resolve_refs(refs, candidate_fetcher=None, doi_checker=None, oa_fetcher=None)`
gains one optional injected dependency. Per reference, the resolution chain is
**additive** (existing order unchanged, one new step appended):

1. **DOI-direct** (existing): `extract_doi` → `doi_checker`; confirmed-exists →
   resolved. (Never marks unresolved on an unconfirmable DOI — 查不到 ≠ 造假.)
2. **Crossref** (existing): `match_any(ref, candidate_fetcher(ref)[:1])` → resolved.
3. **OpenAlex (new)**: only if steps 1–2 did not resolve —
   `match_any(ref, oa_fetcher(ref)[:1])` → resolved.
4. Otherwise → `unresolved`.

The OpenAlex step fires **only on a Crossref miss**, so extra network calls are
bounded by the number of otherwise-unresolved references.

### Component — `_search_reference_openalex(ref, timeout=30)`

- Query `https://api.openalex.org/works?search=<urlencoded ref[:400]>&per_page=1&mailto=<MAILTO>`.
- Parse results into the existing candidate shape: `[{"title": <display_name>, "year": <publication_year as str or None>}]`.
- Return `[]` on any error/empty (never raises). Returns at most 1 candidate
  (top-1, mirroring the Crossref top-1 discipline).
- Reuses module constants `OPENALEX`, `MAILTO` and `http_get_json` already in
  `verify.py`.

### `resolve_refs` change

```python
def resolve_refs(refs, candidate_fetcher=None, doi_checker=None, oa_fetcher=None):
    candidate_fetcher = candidate_fetcher or _search_reference_candidates
    doi_checker = doi_checker or _doi_exists
    oa_fetcher = oa_fetcher or _search_reference_openalex
    unresolved = []
    for ref in refs:
        doi = extract_doi(ref)
        if doi and doi_checker(doi) is True:
            continue
        if match_any(ref, (candidate_fetcher(ref) or [])[:1]):
            continue
        if match_any(ref, (oa_fetcher(ref) or [])[:1]):   # NEW: second source
            continue
        unresolved.append(ref)
    return {"provided_checked": len(refs), "provided_unresolved": unresolved}
```

Return shape unchanged (`provided_checked`, `provided_unresolved`).

## Data flow

`pdf-extract` references → `resolve_refs` → per ref: DOI / Crossref / OpenAlex →
`provided_unresolved`. Mode C reads `refs_unresolved` (count) as before; the
count should be lower (fewer FPs) but its meaning ("could not confirm") is
unchanged.

## Error handling

`_search_reference_openalex` guards all network/parse errors → `[]` (a miss,
never a crash, never a false resolution). `match_any` already guards empty
candidate lists.

## Testing (TDD; injectable units = hard gate)

Unit (`paper-verify/test_verify.py`), all with injected fetchers (no network):
- **OpenAlex rescues a Crossref miss:** `candidate_fetcher` returns no match,
  `oa_fetcher` returns the matching title → ref resolved (not in unresolved).
- **Both sources miss → unresolved:** neither returns a matching candidate.
- **Fake stays unresolved:** `oa_fetcher` returns a *non-matching* title for a
  fabricated ref → `match_any` rejects → unresolved (recall protection).
- **DOI-direct still wins first:** confirmed DOI → resolved without calling
  either title fetcher.
- **Crossref hit short-circuits:** Crossref matches → `oa_fetcher` not consulted
  (assert via a fetcher that records calls / raises if called).
- `_search_reference_openalex` parses an injected `http_get_json` result into
  `[{"title","year"}]` and returns `[]` on error (monkeypatch `http_get_json`).

No regression: existing 28 unit + 2 integration tests stay green; `resolve_refs`
return shape unchanged.

Measurement (not pass/fail):
- Re-run `eval/eval_c1.py datasets/c1_references_hard.jsonl` → **recall must hold
  at ~0.82**; record FP (expect ≤ before, hopefully lower). Re-run easy too.
- Re-run `eval/modec_c1_run.py` → expect BitNet/LoRA unresolved ratios to drop
  materially (the real C1-FP win). Record before→after in
  `eval/results-2026-06.json` (`c1_second_resolver`) + a calibration-doc note.
- **Recall gate:** if hard recall drops below ~0.80 (fakes spuriously matched via
  OpenAlex), STOP — tighten or drop the OpenAlex step. This is the round-② top-N
  lesson; do not ship a recall regression.

## Sync & discipline

- Sync `paper-verify/verify.py` to the live skill.
- Honest: the second resolver lowers FP but a remaining unresolved is still
  "could not confirm," not "fake." `refs_unresolved` stays advisory,
  non-decisive. Record the actual before→after, including recall.
- Local commits only; do not push until the user says so.

## Open / deferred

- Paper-level second resolver for too-new papers (variant (a)): deferred.
- Searching OpenAlex with an extracted title instead of the full ref string:
  start with full ref (consistent with the Crossref call); revisit only if
  measurement shows it underperforms.
