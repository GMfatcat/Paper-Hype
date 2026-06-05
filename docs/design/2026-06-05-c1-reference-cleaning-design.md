# C1 reference cleaning — design spec (2026-06-05)

## Goal

Strip arXiv-HTML citation-key noise from extracted references at the
`pdf-extract` source, so Crossref `query.bibliographic` can match the real
reference and C1 false-positives drop — without hurting the calibrated C1 recall
(~0.82).

## Problem (measured)

The 20-paper Mode C C1 end-to-end test showed legitimate papers running
12–55% of references "unresolved" — all false positives. Inspecting BitNet's
raw arXiv-HTML references shows each real reference is prefixed by a
**citation key**: an author-initial abbreviation + bracketed year/index, e.g.:

```
BZB + [19] Yonatan Bisk, Rowan Zellers, ...
Com [23] Together Computer. Redpajama: ...
FAHA [23] Elias Frantar, Saleh Ashkboos, ...
MXBS [16] Stephen Merity, ...
```

The real reference begins after the key. KAN, whose extraction lacked these
keys, ran only 12.5% unresolved. So the dominant driver is extraction noise,
fixable by stripping the leading key before Crossref sees the string.

## Scope

- **In:** one pure function `clean_reference(s)` in `pdf-extract/extract.py`,
  applied to every emitted reference at the single output chokepoint; tests;
  a before→after re-measurement; live sync.
- **Out (conservative):** author-year inline prefixes like `Allen-Zhu & Li (2019)`,
  trailing URLs, mid-string noise. Only the well-characterized *leading*
  citation-key / bare-index pattern is stripped. Aggressive cleaning is a
  possible later round if measurement shows it is needed.
- **Out:** any change to `paper-verify` matching logic (that was the prior C1
  round; calibration showed tuning the matcher trades recall). Cleaning is the
  lever here.

## Architecture

`extract()` builds a reference list per source (arxiv_html / grobid /
regex_fallback / pdf_textlayer) and returns through a single helper `_result(...)`.
Add cleaning **inside `_result`** so all sources are cleaned uniformly and there
is exactly one place to reason about. GROBID/clean refs are unaffected (the
pattern only matches leading citation-key noise → idempotent no-op on clean
input).

### Component — `clean_reference` (pure, no network)

```
clean_reference(s) -> str
```

Behavior:
1. `None`/empty → `""`.
2. Strip a leading citation key: regex
   `^[A-Z][A-Za-z]{0,7}(?:\s*\+)?\s*\[\d{1,4}\]\s+`
   (matches `BZB + [19] `, `Com [23] `, `FAHA [23] `, `MXBS [16] `).
3. Else strip a leading bare index: `^\[\d{1,4}\]\s+` (matches `[12] `).
4. `.strip()` the result.
5. Idempotent: `clean_reference(clean_reference(x)) == clean_reference(x)`.
6. Conservative: if neither leading pattern matches, return the input trimmed,
   unchanged otherwise. Author-year prefixes (`Allen-Zhu & Li (2019) `) are NOT
   stripped.

### Integration

In `_result(query, ok, source, coverage, text_layer, fulltext, refs, notes,
references_source)`: replace the stored refs with
`[c for c in (clean_reference(r) for r in (refs or [])) if c]`. `references_count`
is then the cleaned, non-empty count. No other call sites change.

## Data flow

`extract()` → per-source refs (possibly dirty) → `_result` cleans each → output
`references` are clean; downstream `paper-verify --refs` / Mode C C1 see clean
strings.

## Error handling

`clean_reference` never raises (guards None/empty; pure regex). Non-matching
input passes through trimmed. A reference that is *only* a citation key (no body)
cleans to `""` and is dropped — correct (it carried no citation).

## Testing (TDD; pure-function unit = hard gate)

Unit (`pdf-extract/test_extract.py`):
- strips `BZB + [19] ` / `Com [23] ` / `FAHA [23] ` / `MXBS [16] ` → body only.
- strips bare `[12] ` → body.
- leaves `Vaswani et al. Attention Is All You Need. 2017.` unchanged.
- leaves `Allen-Zhu & Li (2019) Zeyuan Allen-Zhu ...` unchanged (conservative).
- `None`/`""` → `""`.
- idempotent on a dirty input.
- `_result` drops a key-only reference that cleans to empty.

No regression: existing `test_extract.py` stays green.

Measurement (not a pass/fail test):
- Re-run `eval/modec_c1_run.py` (BitNet/KAN/LoRA) → record before→after
  unresolved ratios. Expect BitNet's ~0.50 to drop materially; KAN ~unchanged.
- Re-run `eval/eval_c1.py` on the c1 calibration set → confirm recall/FP
  unchanged (those refs come from Crossref reference lists and carry no
  citation-key prefix, so cleaning is a no-op there). Record in
  `eval/results-2026-06.json` (a `c1_cleaning` note) and the calibration doc.

## Sync & discipline

- Sync `pdf-extract/extract.py` to the live skill
  (`C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\pdf-extract\extract.py`).
- Honest: conservative cleaner targets only the documented pattern; LoRA-style
  author-year prefixes may remain unresolved (left for round ③ or stays
  advisory). `refs_unresolved` remains advisory, non-decisive.
- Local commits only; do not push until the user says so.

## Open / deferred

- Aggressive cleaning (author-year prefixes, URLs): deferred pending measurement.
- Second resolver source (Semantic Scholar / Crossref-direct on OpenAlex miss):
  the next round (③), independent of this one.
