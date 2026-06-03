# Design Spec — `paper-verify`: structured-API verification backbone (方向 #1)

- **Date:** 2026-06-03
- **Status:** Design approved; pending implementation plan
- **Part of:** roadmap 1→2→4. This is **#1** (API backbone). #2 = PDF full-text extraction, #4 = Mode B batch — each gets its own spec later and both build on this.
- **Affects skill:** `dissecting-paper-hype` (Mode C primarily; Mode B reference checks; future batch modes)
- **One-line:** A deterministic, Dockerized `paper-verify` tool that resolves a paper via OpenAlex + ORCID and returns structured **facts + boolean red-flags** for the integrity checks C1/C4/C5 + author identity — replacing fragile ad-hoc web-scraping with reproducible API lookups.

---

## 1. Problem & goal

Mode B/C currently verify by having sub-agents call `WebFetch` on web pages. Observed failures: PubPeer returns 403; references reported "查不到" inconsistently; author identity is hard to judge (the **arXiv:2606.02437 "Mind Lab"** case needed author disambiguation we could only do by hand). Web scraping is also **non-reproducible** — the same paper can score differently across runs.

**Goal:** a deterministic backbone that returns clean, structured facts for the API-answerable checks, so C1/C4/C5 and author-identity become accurate and reproducible. The tool decides *facts and flags*, not scores — scoring stays in the Mode C rubric.

**Non-goals (v1):** C2/C3 (AI-trace / tortured-phrase — text-based, wait for #2), deep hallucinated-reference detection (needs the bibliography text from #2), PubPeer/predatory-list integration.

## 2. Form & placement

- Dockerized Python CLI at `skill/paper-verify/` (Dockerfile + `verify.py` + README), mirroring `skill/scrapling-fetcher/`.
- Usage: `docker run --rm paper-verify "<DOI | arXiv id | title>"` → one JSON object on stdout. Diagnostics to stderr.
- No API keys: OpenAlex via the polite pool (include a `mailto` param); ORCID public API.

## 3. Data sources (v1)

- **OpenAlex** — backbone. One work object yields: `is_retracted`; `primary_location.source` (type, `is_in_doaj`, publisher, ISSN); `authorships` (author display_name, ORCID, OpenAlex author id, and per-author `works_count`/`cited_by_count`/last institution via the author object); `referenced_works` count; `cited_by_count`.
- **ORCID public API** — confirm that an author's ORCID (from OpenAlex) resolves to a real record. Authors with no ORCID **and** ~0 prior works are counted as weak-identity signals.

## 4. Pipeline (inside `verify.py`)

1. **Resolve work:**
   - DOI → `GET /works/https://doi.org/<doi>`
   - arXiv id → `GET /works/arxiv:<id>` (fallback: `/works?search=<title>`)
   - title only → `/works?search=<title>`, take best match (report match confidence; if weak, `resolved:false`).
2. **Extract facts** from the work object → C4 (retraction), C5 (venue), authors, C1-context (referenced_works count, cited_by_count).
3. **ORCID confirmation:** for each author with an ORCID, hit ORCID public API to confirm the record exists; mark `orcid_verified`. Tally authors with neither ORCID nor prior works.
4. **Optional `--refs <file|json>`** (reserved for #2): batch-resolve a list of reference strings against OpenAlex/Crossref; report how many do not resolve (`provided_unresolved`). Without it, only citation-graph stats are returned.
5. **Compute boolean red-flags** (§5).
6. **Emit JSON** (§6).

## 5. Red-flags (boolean; tool sets them, rubric consumes them)

| Flag | Condition | Maps to |
|---|---|---|
| `retracted` | OpenAlex `is_retracted == true` (or EoC found) | C4 (decisive → 🔴 anchor) |
| `not_in_doaj_journal` | source type == journal AND `is_in_doaj == false` AND publisher unknown/低訊號 | C5 |
| `venue_repository_only` | only location is a preprint repository (e.g. arXiv) | C5 (固有 caveat, 非紅旗 — informational) |
| `author_identity_weak` | share of authors with **no ORCID and works_count ≤ 1** exceeds a threshold (default **≥ 60%** of ≥ 5 authors) | C5 / author |
| `work_not_found` | identifier did not resolve in OpenAlex | **informational, NOT fraud** (often "too new") |
| `refs_unresolved` | (only if `--refs` given) count of provided refs not matching any work | C1 |

Threshold note: `author_identity_weak` default = **≥60% of authors lack both ORCID and a publication history, and the author count ≥5**. Tunable; surfaced in output as the computed ratio so the rubric/reader can judge.

## 6. Output JSON (shape)

```json
{
  "query": "<input>",
  "resolved": true,
  "openalex_id": "W...",
  "title": "...",
  "retraction": {"is_retracted": false, "note": ""},
  "venue": {"name": "...", "type": "journal|conference|repository", "is_in_doaj": true, "publisher": "...", "issn": ["..."]},
  "authors": [{"name": "...", "orcid": "0000-...", "orcid_verified": true, "works_count": 42, "institution": "..."}],
  "references": {"referenced_works_count": 35, "cited_by_count": 12, "provided_checked": 0, "provided_unresolved": []},
  "flags": {"retracted": false, "not_in_doaj_journal": false, "venue_repository_only": true,
            "author_identity_weak": false, "author_weak_ratio": 0.0, "work_not_found": false, "refs_unresolved": 0},
  "notes": ["resolved via OpenAlex by DOI", "2 authors lacked ORCID"]
}
```

## 7. Honesty guardrails (carried into the tool + skill)

- **Not found ≠ fraud.** Brand-new arXiv papers (days old) are often not yet in OpenAlex → `resolved:false, work_not_found:true, note:"too new / not indexed"`. The skill must **fall back to existing WebFetch checks**, not treat this as a flag. (Most of the 2026-06-01/02 batch we scanned would hit this.)
- **No ORCID ≠ fake author** — only meaningful in aggregate; always emit the computed ratio, never a verdict on an individual.
- Rate limits: OpenAlex polite pool (`mailto`), modest ORCID calls, cache within a run.
- The tool emits facts/flags only; **all scoring/verdicts stay in the Mode C rubric** (incl. the decisive-flag anchoring: `retracted` → 🔴).

## 8. Integration into the skill

- **Mode C** 取文/拆解: call `paper-verify <id>` once; feed `facts+flags` into C1/C4/C5 reasoning. C2/C3 remain text-based.
- **Mode B**: when a post cites a paper, use `paper-verify` to confirm existence / retraction / venue.
- **Template F** (C1/C4/C5 sub-agent prompts): "call `paper-verify` first and use its JSON; only fall back to manual WebFetch when `resolved:false`."
- **integrity-signals.md**: record the OpenAlex/ORCID endpoints used.
- **SKILL.md** Mode C 取文 step + the batch mode benefit (deterministic, fast) noted.
- The existing `scrapling-fetcher` (社群貼文) and new `paper-verify` (論文事實) are two separate adapters; do not merge.

## 9. Components / files

- **Create:** `skill/paper-verify/{Dockerfile, verify.py, README.md}`
- **Modify:** `skill/references/templates.md` (F), `skill/references/integrity-signals.md` (endpoints), `skill/SKILL.md` (Mode C 取文/pipeline; note tool in batch mode)

## 10. Testing (RED→GREEN, skill-style)

Run `verify.py` directly on known cases and assert the flags:

| Case | Identifier | Expected |
|---|---|---|
| Clean, indexed | GraphCast `10.1126/science.adi2336` | resolved; `is_retracted:false`; authors with ORCID; no weak-identity flag |
| Retracted | Lancet Surgisphere `10.1016/S0140-6736(20)31180-6` | `retracted:true` 🚩 |
| Predatory/low-index venue | a known non-DOAJ predatory-journal paper | `not_in_doaj_journal:true` 🚩 |
| Weak author identity | arXiv:2606.02437 (Mind Lab) | high `author_weak_ratio`, `author_identity_weak:true` 🚩 (if indexed; else `work_not_found` → fallback) |
| Too new | a paper submitted in the last 1–2 days | `resolved:false`, `work_not_found:true`, note "too new" → skill falls back, **no fraud flag** |

GREEN-integration check: a Mode C run that calls `paper-verify` produces the same verdict as before on the retracted/clean cases, but now grounded in API facts and reproducible across runs.

## 11. Roadmap linkage

- **#2 PDF extraction** will feed `--refs` (bibliography strings) → completes C1 hallucinated-ref detection; also unlocks C2/C3 on paywalled/image PDFs.
- **#4 Mode B batch** gains determinism/speed from this backbone.
