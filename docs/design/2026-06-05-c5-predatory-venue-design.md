# C5 predatory / hijacked venue detection — design spec (2026-06-05)

## Goal

Give Mode C a **deterministic** venue-integrity signal that distinguishes a
genuinely predatory or hijacked journal from a merely-not-in-DOAJ one. The
20-paper Mode C test showed today's `not_in_doaj_journal` flag fires identically
on a Beall's-List journal (IJISRT) and on reputable subscription journals (BMJ,
Review of Economic Studies), so it cannot drive a C5 verdict. This adds bundled
watchlists matched by ISSN/name to `paper-verify`, plus rubric changes in the
skill so a confirmed hit actually moves the score.

## Scope

- **In:** bundled watchlists (Beall's standalone journals, Beall's predatory
  publishers, hijacked journals); a pure matcher in `verify.py`; new flags;
  a reproducible build script; SKILL Mode C rubric update; tests + a small C5
  calibration set.
- **Out:** live scraping of predatory lists at runtime (no authoritative API;
  non-deterministic). DOAJ "positive" signal stays as-is — it already arrives
  live via OpenAlex `is_in_doaj`, so the "hybrid" is: bundled lists (new,
  deterministic) **+** existing live DOAJ. No new live calls are added.
- **Out:** fuzzy name matching (FP risk — the very bug we are fixing). Name
  matching is exact-after-normalization only.

## Architecture

Network-first verifier unchanged. After `extract_facts`, the venue is matched
against in-memory watchlists loaded once from a committed JSON snapshot. Match
result is attached to `facts.venue.watchlist`; `compute_flags` reads it to set
new booleans. Scoring (turning flags into 0–100 + lights) stays in the SKILL,
not the tool — the tool only emits flags + provenance.

### Data file — `skill/paper-verify/data/watchlists.json`

Single JSON file (carries provenance meta in one place; one load):

```json
{
  "meta": {
    "snapshot_date": "2026-06-05",
    "sources": {
      "predatory_journals": "https://beallslist.net/standalone-journals/",
      "predatory_publishers": "https://beallslist.net/",
      "hijacked_journals": "https://retractionwatch.com/the-retraction-watch-hijacked-journal-checker/"
    },
    "note": "Beall's List is community-maintained and contested (false inclusions exist); a hit is a lead, not a verdict. Refresh: re-run build_watchlists.py."
  },
  "predatory_journals": [
    {"name": "International Journal of Innovative Science and Research Technology", "issn": ["2456-2156"]}
  ],
  "predatory_publishers": [
    {"name": "OMICS Publishing Group"}
  ],
  "hijacked_journals": [
    {"name": "<journal>", "issn": ["<clone-issn>"]}
  ]
}
```

- `issn` is a list (a journal can have print+electronic ISSN); may be empty when
  the source lacks it → that entry is name-only.
- ISSNs are stored normalized to `NNNN-NNNN` upper-case `X`.

### Build script — `skill/paper-verify/build_watchlists.py`

Reproducible generator: fetches the three sources, parses entries, writes
`data/watchlists.json` with `snapshot_date` from an injected date (no
`Date.now()`-style hidden state — date passed as arg/const so the commit is
deterministic). Network-dependent, run manually; documented as the refresh
step. The committed JSON is the source of truth for the tool; the build script
is how it is regenerated. If a source is unreachable the script keeps the prior
section and logs which sections it refreshed (no silent truncation).

### Matcher — pure functions in `verify.py`

```
_norm_name(s)      # lower; strip punctuation -> space; collapse ws; drop leading "the "
_norm_issn(s)      # uppercase, ensure NNNN-NNNN form; return None if not ISSN-shaped
load_watchlists(path=DEFAULT_WATCHLISTS)
    -> {"issn": {issn: category}, "name": {normname: category},
        "publisher": {normname: "predatory"}, "meta": {...}, "entries": {...}}
    # category in {"hijacked", "predatory"}; index built once
match_venue(venue, watchlists)
    -> None | {"category": "hijacked"|"predatory",
               "list": "hijacked_journals"|"predatory_journals"|"predatory_publishers",
               "matched_by": "issn"|"name"|"publisher",
               "value": "<the matched issn or name>",
               "source": "<url>", "snapshot_date": "<date>"}
```

**Precedence** (first hit wins): hijacked-by-ISSN → hijacked-by-name →
predatory-journal-by-ISSN → predatory-journal-by-name → predatory-publisher-by-name.
ISSN beats name within each tier. `hijacked` outranks `predatory` so a clone is
never downgraded to a mere predatory hit.

`DEFAULT_WATCHLISTS = os.path.join(os.path.dirname(__file__), "data", "watchlists.json")`.
Loader is resilient: missing/unparseable file → empty watchlists + a note, never
a crash (tool must still resolve facts without the lists).

### Flags — `compute_flags` additions

```
venue_hijacked:   bool   # facts.venue.watchlist.category == "hijacked"
venue_predatory:  bool   # facts.venue.watchlist.category == "predatory"
not_in_doaj_journal: bool # UNCHANGED field, kept for back-compat; now advisory only
```

Provenance lives in `facts.venue.watchlist` (the match dict above, or null), so
the Mode C dossier can cite list + source + snapshot_date + matched_by. Existing
fields and the `verify()` return shape are otherwise unchanged (Mode C / eval
compatibility).

### Wiring — `verify()`

After `facts = extract_facts(work)` and author enrichment: load watchlists once
(module-level cache acceptable), `facts["venue"]["watchlist"] = match_venue(...)`,
then `compute_flags(facts)`. `resolved:false` path adds the two new flags as
`false` for shape consistency.

### Scoring — SKILL Mode C rubric (skill/SKILL.md + references/integrity-signals.md)

- `venue_hijacked` → **decisive red flag**, anchors to 🔴 (71–100) like a
  confirmed retraction (a hijacked-clone venue is fraud-adjacent).
- `venue_predatory` → fills the C5 cap (15 pts) and pushes toward 🟠; **not**
  auto-RED on its own (Beall's List is contested / has false inclusions) —
  combined with other confirmed flags it can still reach 🔴 via normal summation.
- `not_in_doaj_journal` alone → minor/advisory (no longer implies predatory);
  reputable subscription journals trip it legitimately.
- Dossier must cite the watchlist source + snapshot_date and state that list
  membership is a lead, not proof.

## Testing (TDD; pure-function units are the hard gate)

**Pure units (no network):**
- `_norm_name`: punctuation/case/whitespace/"the " cases.
- `_norm_issn`: valid, `X` checkdigit, malformed → None.
- `load_watchlists`: parses a small fixture; missing file → empty + note.
- `match_venue`:
  - predatory-journal ISSN hit (IJISRT 2456-2156) → category predatory.
  - predatory-journal name hit when ISSN absent.
  - predatory-publisher name hit.
  - hijacked ISSN hit → category hijacked.
  - **hijacked outranks predatory** when both could match.
  - **regression (the bug we fix): BMJ and Review of Economic Studies → None**
    (no match), even though they are not-in-DOAJ.
  - empty/garbage venue → None.

**Integration (network, marked):** IJISRT DOI → `venue_predatory` true; BMJ DOI →
both new flags false; one known hijacked journal → `venue_hijacked` true.

**No regression:** existing `test_verify.py` (28 unit + 2 integration) stays green;
`verify()` return shape unchanged.

**Calibration:** small `eval/datasets/c5_venues.jsonl` (the IJISRT×4 predatory +
BMJ/RES/NAR/CVPR legit from the 20-paper test, plus ≥1 hijacked) → `eval/eval_c5.py`
reports precision / FP (positive class = "flagged predatory-or-hijacked").
Target: 0 FP on the reputable journals (the whole point); recall reported
honestly. Numbers → `eval/results-2026-06.json` + a line in calibration doc.

## Sync & discipline

- Sync `verify.py` **and** the new `data/watchlists.json` to the live skill
  (`C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\paper-verify\`); live
  SKILL.md keeps its own absolute paths (no whole-file copy repo→live).
- `eval/` and `docs/` are repo-level, not synced into the installed skill.
- Honest: a watchlist hit is a lead, not an accusation; Beall's is contested;
  publish FP numbers including unflattering ones; refresh step documented.
- Design/build stays local until the user says "push".

## Open / deferred

- Live DOAJ ISSN confirmation call: deferred (marginal; `is_in_doaj` already
  covers the positive signal). 
- Fake-impact-factor detection: out of scope this round.
