# C5 Predatory / Hijacked Venue Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `paper-verify` a deterministic, list-based C5 signal that tells a predatory/hijacked journal apart from a merely-not-in-DOAJ one.

**Architecture:** Bundled `data/watchlists.json` (Beall's journals + publishers, hijacked journals) is loaded once and matched against a work's venue by ISSN (primary) then normalized name (secondary). Pure matcher functions live in `verify.py`; `compute_flags` emits two new booleans (`venue_hijacked`, `venue_predatory`); provenance is attached to `facts.venue.watchlist`. Scoring stays in the skill rubric. A reproducible `build_watchlists.py` regenerates the JSON; `eval/eval_c5.py` measures FP/precision.

**Tech Stack:** Python 3 stdlib only (`json`, `re`, `os`, `urllib`); pytest; existing `verify.py` patterns.

**Spec:** `docs/design/2026-06-05-c5-predatory-venue-design.md`

**Conventions (match existing repo):**
- All work in `D:\paper\hype_experiment_3\repo`. Run pytest from `skill/paper-verify/` (that's where `pytest.ini` + `test_verify.py` live and how the 28 existing tests run).
- CLI mains already do `sys.stdout.reconfigure(encoding="utf-8")`; any new script that prints must do the same (Windows cp950 crash otherwise).
- Pure functions = hard TDD gate (unit, no network). Integration tests carry `@pytest.mark.integration` and are NOT required to pass offline.
- `verify()` return shape must NOT change (Mode C + eval depend on it). New flags are additive.
- Commit after each task. Do NOT push (user gates push separately). Co-author trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `skill/paper-verify/data/watchlists.json` | Committed seed snapshot: 3 list sections + `meta` (sources, snapshot_date) | Create |
| `skill/paper-verify/verify.py` | Add `_norm_name`, `_norm_issn`, `load_watchlists`, `match_venue`; extend `compute_flags`; wire `verify()` | Modify |
| `skill/paper-verify/test_verify.py` | Unit + regression + integration tests for the above | Modify |
| `skill/paper-verify/build_watchlists.py` | Reproducible generator for `watchlists.json` | Create |
| `eval/datasets/c5_venues.jsonl` | Labeled venues (predatory / hijacked / legit) | Create |
| `eval/eval_c5.py` | Run verify over the set; report precision / FP | Create |
| `eval/results-2026-06.json` | Add `c5` results block | Modify |
| `skill/SKILL.md` | C5 rubric: hijacked→decisive 🔴, predatory→amber, not_in_doaj→advisory | Modify |
| `skill/references/integrity-signals.md` | C5 signal notes reflect watchlists + honesty caveat | Modify |

---

## Task 1: Watchlist data file + normalizers

**Files:**
- Create: `skill/paper-verify/data/watchlists.json`
- Modify: `skill/paper-verify/verify.py` (add pure helpers after the existing "Pure helpers" block, near `_parse_candidates`)
- Test: `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Create the seed data file**

Create `skill/paper-verify/data/watchlists.json` with well-documented entries only (IJISRT is on Beall's List; OMICS was FTC-fined for predatory practices; Bothalia is a documented hijacked-journal case, Abalkina 2021). `build_watchlists.py` (Task 5) repopulates the full lists later.

```json
{
  "meta": {
    "snapshot_date": "2026-06-05",
    "sources": {
      "predatory_journals": "https://beallslist.net/standalone-journals/",
      "predatory_publishers": "https://beallslist.net/",
      "hijacked_journals": "https://retractionwatch.com/the-retraction-watch-hijacked-journal-checker/"
    },
    "note": "Beall's List is community-maintained and contested (false inclusions exist). A hit is a lead, not a verdict. Refresh by re-running build_watchlists.py."
  },
  "predatory_journals": [
    {"name": "International Journal of Innovative Science and Research Technology", "issn": ["2456-2156"]}
  ],
  "predatory_publishers": [
    {"name": "OMICS Publishing Group"}
  ],
  "hijacked_journals": [
    {"name": "Bothalia", "issn": ["0006-8241"]}
  ]
}
```

- [ ] **Step 2: Write failing tests for `_norm_name` and `_norm_issn`**

Add to `test_verify.py`:

```python
def test_norm_name():
    assert verify._norm_name("The Lancet!") == "lancet"
    assert verify._norm_name("  Nucleic   Acids  Research ") == "nucleic acids research"
    assert verify._norm_name("Bio-Medical & Eng.") == "bio medical eng"
    assert verify._norm_name(None) == ""

def test_norm_issn():
    assert verify._norm_issn("2456-2156") == "2456-2156"
    assert verify._norm_issn("24562156") == "2456-2156"
    assert verify._norm_issn("0006-821x") == "0006-821X"
    assert verify._norm_issn("not-an-issn") is None
    assert verify._norm_issn(None) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py::test_norm_name test_verify.py::test_norm_issn -v`
Expected: FAIL with `AttributeError: module 'verify' has no attribute '_norm_name'`

- [ ] **Step 4: Implement `_norm_name` and `_norm_issn`**

Add to `verify.py` after `_parse_candidates`:

```python
# ---------------------------------------------------------------------------
# C5 venue watchlists (predatory / hijacked) — pure helpers
# ---------------------------------------------------------------------------

def _norm_name(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    if s.startswith("the "):
        s = s[4:]
    return re.sub(r"\s+", " ", s)

def _norm_issn(s):
    if not s:
        return None
    raw = re.sub(r"[^0-9xX]", "", s).upper()
    if len(raw) != 8 or not re.fullmatch(r"\d{7}[\dX]", raw):
        return None
    return raw[:4] + "-" + raw[4:]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py::test_norm_name test_verify.py::test_norm_issn -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Write failing test for `load_watchlists`**

```python
def test_load_watchlists_fixture(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(_json.dumps({
        "meta": {"snapshot_date": "2026-06-05", "sources": {}},
        "predatory_journals": [{"name": "Fake Journal", "issn": ["1111-1111"]}],
        "predatory_publishers": [{"name": "Bad Publisher"}],
        "hijacked_journals": [{"name": "Cloned J", "issn": ["2222-2222"]}],
    }), encoding="utf-8")
    wl = verify.load_watchlists(str(p))
    assert wl["issn"]["1111-1111"] == "predatory"
    assert wl["issn"]["2222-2222"] == "hijacked"
    assert wl["name"]["fake journal"] == "predatory"
    assert wl["publisher"]["bad publisher"] == "predatory"
    assert wl["meta"]["snapshot_date"] == "2026-06-05"

def test_load_watchlists_missing_file():
    wl = verify.load_watchlists("/no/such/watchlists.json")
    assert wl["issn"] == {} and wl["name"] == {} and wl["publisher"] == {}
    assert "note" in wl["meta"]
```

- [ ] **Step 7: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py::test_load_watchlists_fixture test_verify.py::test_load_watchlists_missing_file -v`
Expected: FAIL (`no attribute 'load_watchlists'`)

- [ ] **Step 8: Implement `load_watchlists`**

Add to `verify.py` (after the normalizers):

```python
DEFAULT_WATCHLISTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "data", "watchlists.json")

def load_watchlists(path=DEFAULT_WATCHLISTS):
    empty = {"issn": {}, "name": {}, "publisher": {},
             "meta": {"note": "watchlists unavailable"}, "entries": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return empty
    issn_idx, name_idx, pub_idx, entries = {}, {}, {}, {}
    def add_journals(section, category):
        for e in data.get(section) or []:
            nm = _norm_name(e.get("name"))
            if nm:
                name_idx.setdefault(nm, category)
                entries[(category, "name", nm)] = e
            for raw in e.get("issn") or []:
                iss = _norm_issn(raw)
                if iss:
                    issn_idx.setdefault(iss, category)
                    entries[(category, "issn", iss)] = e
    add_journals("hijacked_journals", "hijacked")     # add hijacked first so its
    add_journals("predatory_journals", "predatory")   # ISSN/name wins setdefault
    for e in data.get("predatory_publishers") or []:
        nm = _norm_name(e.get("name"))
        if nm:
            pub_idx.setdefault(nm, "predatory")
            entries[("predatory", "publisher", nm)] = e
    return {"issn": issn_idx, "name": name_idx, "publisher": pub_idx,
            "meta": data.get("meta") or {}, "entries": entries}
```

Note: `import os` already exists at top of `verify.py`; `json` and `re` too. No new imports for this task.

- [ ] **Step 9: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py::test_load_watchlists_fixture test_verify.py::test_load_watchlists_missing_file -v`
Expected: PASS (2 passed)

- [ ] **Step 10: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/data/watchlists.json skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): C5 watchlist data + normalizers + loader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `match_venue` matcher (precedence + regression)

**Files:**
- Modify: `skill/paper-verify/verify.py` (add `match_venue` after `load_watchlists`)
- Test: `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Write failing tests**

These encode every precedence path AND the bug being fixed (legit subscription journals must NOT match).

```python
def _wl():
    # in-memory watchlists built directly (no file)
    return {
        "issn": {"2456-2156": "predatory", "0006-8241": "hijacked"},
        "name": {"international journal of innovative science and research technology": "predatory",
                 "bothalia": "hijacked"},
        "publisher": {"omics publishing group": "predatory"},
        "meta": {"snapshot_date": "2026-06-05",
                 "sources": {"predatory_journals": "https://beallslist.net/standalone-journals/"}},
        "entries": {},
    }

def test_match_venue_predatory_by_issn():
    v = {"name": "Whatever", "issn": ["2456-2156"], "publisher": "X"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "predatory" and hit["matched_by"] == "issn"

def test_match_venue_predatory_by_name_when_no_issn():
    v = {"name": "International Journal of Innovative Science and Research Technology",
         "issn": [], "publisher": "X"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "predatory" and hit["matched_by"] == "name"

def test_match_venue_predatory_by_publisher():
    v = {"name": "Some Journal of Stuff", "issn": ["9999-9999"], "publisher": "OMICS Publishing Group"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "predatory" and hit["matched_by"] == "publisher"

def test_match_venue_hijacked_by_issn():
    v = {"name": "Bothalia", "issn": ["0006-8241"], "publisher": "X"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "hijacked" and hit["matched_by"] == "issn"

def test_match_venue_hijacked_outranks_predatory():
    # a venue that is both a hijacked ISSN and a predatory name -> hijacked wins
    wl = _wl()
    wl["name"]["bothalia"] = "predatory"   # contrive a name collision
    v = {"name": "Bothalia", "issn": ["0006-8241"], "publisher": "X"}
    hit = verify.match_venue(v, wl)
    assert hit["category"] == "hijacked"

def test_match_venue_legit_subscription_no_match():
    # THE REGRESSION: BMJ / Review of Economic Studies are not-in-DOAJ but NOT predatory
    for v in ({"name": "BMJ", "issn": ["0959-8138", "1756-1833"], "publisher": "BMJ"},
              {"name": "The Review of Economic Studies", "issn": ["0034-6527"], "publisher": "Oxford University Press"}):
        assert verify.match_venue(v, _wl()) is None

def test_match_venue_empty():
    assert verify.match_venue({}, _wl()) is None
    assert verify.match_venue(None, _wl()) is None
```

- [ ] **Step 2: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k match_venue -v`
Expected: FAIL (`no attribute 'match_venue'`)

- [ ] **Step 3: Implement `match_venue`**

Add to `verify.py` after `load_watchlists`:

```python
def match_venue(venue, watchlists):
    venue = venue or {}
    issns = [i for i in (_norm_issn(x) for x in (venue.get("issn") or [])) if i]
    nm = _norm_name(venue.get("name"))
    pub = _norm_name(venue.get("publisher"))
    meta = watchlists.get("meta") or {}
    src = (meta.get("sources") or {})
    sd = meta.get("snapshot_date")

    def hit(category, matched_by, value, list_name):
        return {"category": category, "list": list_name, "matched_by": matched_by,
                "value": value, "source": src.get(list_name), "snapshot_date": sd}

    # precedence: hijacked (issn -> name) > predatory journal (issn -> name) > predatory publisher
    for iss in issns:
        if watchlists["issn"].get(iss) == "hijacked":
            return hit("hijacked", "issn", iss, "hijacked_journals")
    if nm and watchlists["name"].get(nm) == "hijacked":
        return hit("hijacked", "name", nm, "hijacked_journals")
    for iss in issns:
        if watchlists["issn"].get(iss) == "predatory":
            return hit("predatory", "issn", iss, "predatory_journals")
    if nm and watchlists["name"].get(nm) == "predatory":
        return hit("predatory", "name", nm, "predatory_journals")
    if pub and watchlists["publisher"].get(pub) == "predatory":
        return hit("predatory", "publisher", pub, "predatory_publishers")
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k match_venue -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): match_venue with hijacked>predatory precedence (BMJ regression locked)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `compute_flags` emits venue_hijacked / venue_predatory

**Files:**
- Modify: `skill/paper-verify/verify.py` (`compute_flags`)
- Test: `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Write failing tests**

The existing `_facts(...)` helper in `test_verify.py` builds a facts dict. Watchlist provenance lives at `facts["venue"]["watchlist"]`.

```python
def test_flags_venue_predatory():
    f = _facts()
    f["venue"]["watchlist"] = {"category": "predatory", "list": "predatory_journals"}
    fl = verify.compute_flags(f)
    assert fl["venue_predatory"] is True
    assert fl["venue_hijacked"] is False

def test_flags_venue_hijacked():
    f = _facts()
    f["venue"]["watchlist"] = {"category": "hijacked", "list": "hijacked_journals"}
    fl = verify.compute_flags(f)
    assert fl["venue_hijacked"] is True
    assert fl["venue_predatory"] is False

def test_flags_venue_clean_no_watchlist():
    fl = verify.compute_flags(_facts())   # no watchlist key
    assert fl["venue_hijacked"] is False and fl["venue_predatory"] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "venue_predatory or venue_hijacked or venue_clean" -v`
Expected: FAIL (`KeyError: 'venue_predatory'`)

- [ ] **Step 3: Implement the flag additions**

In `verify.py` `compute_flags`, the function currently returns a dict with `not_in_doaj_journal`, etc. Add the two flags by reading the watchlist hit. Replace the `return {...}` block of `compute_flags` with this (keeps every existing key unchanged, adds two):

```python
    wl_hit = (venue.get("watchlist") or {})
    wl_cat = wl_hit.get("category")
    return {
        "retracted": bool(facts.get("retraction", {}).get("is_retracted")),
        "not_in_doaj_journal": vtype == "journal" and venue.get("is_in_doaj") is False,
        "venue_repository_only": vtype == "repository",
        "venue_predatory": wl_cat == "predatory",
        "venue_hijacked": wl_cat == "hijacked",
        "author_identity_weak": n >= MIN_AUTHORS and ratio >= WEAK_RATIO,
        "author_weak_ratio": round(ratio, 2),
        "work_not_found": False,
        "refs_unresolved": len(facts.get("references", {}).get("provided_unresolved") or []),
    }
```

(`venue` is already bound earlier in `compute_flags` as `facts.get("venue") or {}`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "venue_predatory or venue_hijacked or venue_clean" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the FULL existing suite — no regression**

Run: `cd skill/paper-verify && python -m pytest -m "not integration" -q`
Expected: all previously-passing unit tests still pass (now 28 + the new ones).

- [ ] **Step 6: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): compute_flags emits venue_predatory / venue_hijacked

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire `verify()` + not-found path + integration

**Files:**
- Modify: `skill/paper-verify/verify.py` (`verify`, and the `work is None` branch's flags)
- Test: `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Write failing test (resolved path attaches watchlist + flags via monkeypatch)**

```python
def test_verify_attaches_watchlist(monkeypatch):
    work = dict(CLEAN_WORK)
    work["primary_location"] = {"source": {"display_name": "International Journal of Innovative Science and Research Technology",
                                           "type": "journal", "is_in_doaj": False,
                                           "issn": ["2456-2156"], "host_organization_name": "IJISRT"}}
    monkeypatch.setattr(verify, "fetch_openalex", lambda i: work)
    monkeypatch.setattr(verify, "enrich_authors", lambda a: a)
    r = verify.verify("10.38124/ijisrt/x")
    assert r["venue"]["watchlist"]["category"] == "predatory"
    assert r["flags"]["venue_predatory"] is True
    assert r["flags"]["venue_hijacked"] is False

def test_verify_not_found_has_new_flags(monkeypatch):
    monkeypatch.setattr(verify, "fetch_openalex", lambda i: None)
    r = verify.verify("2999.99999")
    assert r["flags"]["venue_predatory"] is False
    assert r["flags"]["venue_hijacked"] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "attaches_watchlist or not_found_has_new_flags" -v`
Expected: FAIL (`KeyError: 'watchlist'` and missing flag keys in not-found branch)

- [ ] **Step 3: Implement wiring**

(a) Module-level cached load near `DEFAULT_WATCHLISTS`:

```python
_WATCHLISTS_CACHE = None

def _get_watchlists():
    global _WATCHLISTS_CACHE
    if _WATCHLISTS_CACHE is None:
        _WATCHLISTS_CACHE = load_watchlists()
    return _WATCHLISTS_CACHE
```

(b) In `verify()`, after `facts = extract_facts(work)` and BEFORE `compute_flags`:

```python
    facts["authors"] = enrich_authors(facts["authors"])
    facts["venue"]["watchlist"] = match_venue(facts.get("venue"), _get_watchlists())
    flags = compute_flags(facts)
```

(c) In the `work is None` branch, add the two flags to the inline `"flags"` dict so the shape is consistent:

```python
            "flags": {"retracted": False, "not_in_doaj_journal": False,
                      "venue_repository_only": False, "venue_predatory": False,
                      "venue_hijacked": False, "author_identity_weak": False,
                      "author_weak_ratio": 0.0, "work_not_found": True, "refs_unresolved": 0},
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "attaches_watchlist or not_found_has_new_flags" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Add integration tests (real network; marked)**

```python
@pytest.mark.integration
def test_integration_ijisrt_predatory():
    r = verify.verify("10.38124/ijisrt/ijisrt24apr651")
    assert r["resolved"] is True
    assert r["flags"]["venue_predatory"] is True

@pytest.mark.integration
def test_integration_bmj_not_predatory():
    r = verify.verify("10.1136/bmj-2023-078378")
    assert r["resolved"] is True
    assert r["flags"]["venue_predatory"] is False
    assert r["flags"]["venue_hijacked"] is False
```

- [ ] **Step 6: Run integration (best-effort; network)**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "integration_ijisrt or integration_bmj" -m integration -v`
Expected: PASS if network available. If offline, note it; do not block on it.

- [ ] **Step 7: Run full unit suite — no regression**

Run: `cd skill/paper-verify && python -m pytest -m "not integration" -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): wire watchlist into verify() + not-found flag shape

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Reproducible `build_watchlists.py`

**Files:**
- Create: `skill/paper-verify/build_watchlists.py`
- Test: `skill/paper-verify/test_verify.py` (pure-parse test only; no live fetch in tests)

- [ ] **Step 1: Write failing test for the pure parser pieces**

The builder must expose pure helpers that tests can drive without network:

```python
def test_build_watchlists_merge_keeps_prior_on_missing():
    import build_watchlists as bw
    prior = {"meta": {"snapshot_date": "2025-01-01", "sources": {}},
             "predatory_journals": [{"name": "Old J", "issn": ["1111-1111"]}],
             "predatory_publishers": [], "hijacked_journals": []}
    # fetched: journals OK, publishers/hijacked failed (None) -> keep prior sections
    merged = bw.merge_sections(prior,
                               predatory_journals=[{"name": "New J", "issn": ["2222-2222"]}],
                               predatory_publishers=None,
                               hijacked_journals=None,
                               snapshot_date="2026-06-05")
    assert merged["predatory_journals"] == [{"name": "New J", "issn": ["2222-2222"]}]
    assert merged["predatory_publishers"] == []        # prior kept, not dropped to error
    assert merged["hijacked_journals"] == []           # prior kept
    assert merged["meta"]["snapshot_date"] == "2026-06-05"
    assert merged["meta"]["refreshed"] == ["predatory_journals"]   # only the fetched section
```

- [ ] **Step 2: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py::test_build_watchlists_merge_keeps_prior_on_missing -v`
Expected: FAIL (`No module named 'build_watchlists'`)

- [ ] **Step 3: Implement `build_watchlists.py`**

```python
"""Regenerate skill/paper-verify/data/watchlists.json from public sources.

Reproducible: snapshot_date is passed in (no hidden clock). If a source can't be
fetched, the prior section is kept (no silent truncation); meta.refreshed lists
which sections were actually updated this run.

Usage:
    python build_watchlists.py 2026-06-05        # date is required, explicit
Network-dependent; run manually as the refresh step.
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "watchlists.json")
SOURCES = {
    "predatory_journals": "https://beallslist.net/standalone-journals/",
    "predatory_publishers": "https://beallslist.net/",
    "hijacked_journals": "https://retractionwatch.com/the-retraction-watch-hijacked-journal-checker/",
}
_UA = {"User-Agent": "paper-verify watchlist builder (mailto:paper-verify@example.org)"}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_beall_journals(html):
    # Beall's standalone-journals page lists <li><a ...>Name</a></li> entries.
    names = re.findall(r"<li>\s*<a[^>]*>(.*?)</a>", html, re.I | re.S)
    out = []
    for n in names:
        n = re.sub(r"<[^>]+>", "", n).strip()
        if n:
            out.append({"name": n, "issn": []})
    return out or None


def parse_beall_publishers(html):
    names = re.findall(r"<li>\s*<a[^>]*>(.*?)</a>", html, re.I | re.S)
    out = []
    for n in names:
        n = re.sub(r"<[^>]+>", "", n).strip()
        if n:
            out.append({"name": n})
    return out or None


def parse_hijacked(html):
    # Hijacked Journal Checker exposes name + ISSN pairs; heuristic extraction.
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)
    out = []
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)]
        if not cells:
            continue
        name = cells[0]
        issns = re.findall(r"\d{4}-\d{3}[\dxX]", row)
        if name:
            out.append({"name": name, "issn": issns})
    return out or None


def merge_sections(prior, predatory_journals, predatory_publishers,
                   hijacked_journals, snapshot_date):
    refreshed = []
    result = {"meta": dict(prior.get("meta") or {})}
    sections = {
        "predatory_journals": predatory_journals,
        "predatory_publishers": predatory_publishers,
        "hijacked_journals": hijacked_journals,
    }
    for key, fetched in sections.items():
        if fetched is None:
            result[key] = prior.get(key) or []     # keep prior; no silent loss
        else:
            result[key] = fetched
            refreshed.append(key)
    result["meta"]["snapshot_date"] = snapshot_date
    result["meta"]["sources"] = SOURCES
    result["meta"]["refreshed"] = refreshed
    result["meta"].setdefault(
        "note", "Beall's List is community-maintained and contested. A hit is a lead, not a verdict.")
    return result


def main(snapshot_date):
    try:
        with open(OUT, encoding="utf-8") as f:
            prior = json.load(f)
    except Exception:
        prior = {}
    def safe(parser, key):
        try:
            return parser(fetch(SOURCES[key]))
        except Exception as e:
            print("WARN could not refresh", key, "->", e)
            return None
    merged = merge_sections(
        prior,
        safe(parse_beall_journals, "predatory_journals"),
        safe(parse_beall_publishers, "predatory_publishers"),
        safe(parse_hijacked, "hijacked_journals"),
        snapshot_date,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print("WROTE", OUT, "refreshed:", merged["meta"]["refreshed"])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: python build_watchlists.py <YYYY-MM-DD>")
        sys.exit(2)
    main(sys.argv[1])
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py::test_build_watchlists_merge_keeps_prior_on_missing -v`
Expected: PASS

- [ ] **Step 5: Sanity-run the builder live (best-effort; do NOT overwrite the curated seed if parsing looks wrong)**

Run: `cd skill/paper-verify && python build_watchlists.py 2026-06-05`
Expected: prints `WROTE ... refreshed: [...]`. **Inspect the diff**: if a parser produced garbage (e.g., 0 entries or HTML cruft), `git checkout skill/paper-verify/data/watchlists.json` to restore the curated seed and leave a note that the parser for that source needs work. The curated seed (IJISRT/OMICS/Bothalia) must remain valid either way. Honest: do not commit a watchlist full of parse noise.

- [ ] **Step 6: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/build_watchlists.py skill/paper-verify/test_verify.py skill/paper-verify/data/watchlists.json
git commit -m "feat(paper-verify): reproducible build_watchlists.py (keep-prior on fetch fail)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: C5 calibration set + eval

**Files:**
- Create: `eval/datasets/c5_venues.jsonl`
- Create: `eval/eval_c5.py`
- Modify: `eval/results-2026-06.json`
- Test: none new (eval scripts are run, not unit-tested; they reuse `metrics.py`)

- [ ] **Step 1: Create the labeled dataset**

`eval/datasets/c5_venues.jsonl` — real DOIs from the 20-paper Mode C test, labeled. `expect` = "flagged" means we expect venue_predatory OR venue_hijacked true.

```
{"id": "10.38124/ijisrt/ijisrt24apr651", "venue": "IJISRT", "label": "predatory", "expect": "flagged"}
{"id": "10.38124/ijisrt/ijisrt24may1483", "venue": "IJISRT", "label": "predatory", "expect": "flagged"}
{"id": "10.38124/ijisrt/ijisrt24apr2676", "venue": "IJISRT", "label": "predatory", "expect": "flagged"}
{"id": "10.38124/ijisrt/ijisrt24mar1125", "venue": "IJISRT", "label": "predatory", "expect": "flagged"}
{"id": "10.1136/bmj-2023-078378", "venue": "BMJ", "label": "legit", "expect": "clean"}
{"id": "10.1093/restud/rdae007", "venue": "Review of Economic Studies", "label": "legit", "expect": "clean"}
{"id": "10.1093/nar/gkae268", "venue": "Nucleic Acids Research", "label": "legit", "expect": "clean"}
{"id": "10.1109/cvpr52733.2024.01605", "venue": "CVPR", "label": "legit", "expect": "clean"}
{"id": "10.1126/science.adi2336", "venue": "Science", "label": "legit", "expect": "clean"}
```

Note in the dataset header comment of `eval_c5.py`: a hijacked-journal positive (e.g. a paper published in the cloned *Bothalia*) is hard to obtain a stable DOI for; hijacked detection is covered by unit tests (`test_match_venue_hijacked_by_issn`). If a stable hijacked DOI is found later, add it here.

- [ ] **Step 2: Implement `eval/eval_c5.py`**

```python
"""C5 venue calibration: does the watchlist flag predatory/hijacked venues
without false-positiving reputable journals? positive class = "flagged"
(venue_predatory OR venue_hijacked). Reports precision / recall / FP via metrics.py.
"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skill", "paper-verify"))
import verify
import metrics

def predict(result):
    fl = result.get("flags") or {}
    return "flagged" if (fl.get("venue_predatory") or fl.get("venue_hijacked")) else "clean"

def run(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    y_true, y_pred = [], []
    for r in rows:
        res = verify.verify(r["id"])
        pred = predict(res)
        y_true.append("flagged" if r["expect"] == "flagged" else "clean")
        y_pred.append(pred)
        print(f'{r["venue"]:30} expect={r["expect"]:7} got={pred:7} resolved={res.get("resolved")}')
    m = metrics.confusion(y_true, y_pred, positive="flagged")
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return m

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "datasets", "c5_venues.jsonl")
    run(p)
```

Before writing, confirm `metrics.py` exposes a `confusion(y_true, y_pred, positive=...)` returning precision/recall/false_positive_rate/tp/fp/tn/fn (the other eval_*.py use it). If the function name differs, match the existing one.

- [ ] **Step 3: Run the eval (network)**

Run: `cd eval && python eval_c5.py`
Expected: the 4 IJISRT rows `got=flagged`, the 5 legit rows `got=clean`; `false_positive_rate: 0.0`. If any legit venue shows `flagged`, STOP — that's the exact FP we are trying to avoid; investigate (likely a too-broad name entry) before recording numbers.

- [ ] **Step 4: Record results honestly**

Add a `c5` block to `eval/results-2026-06.json` with the confusion output + `"run_date": "2026-06-05"` + a `note` (e.g. "predatory recall N/4 on IJISRT; 0 FP on reputable journals; hijacked path unit-tested only — no stable hijacked DOI in set"). Use the ACTUAL numbers printed, including if recall < 4/4.

- [ ] **Step 5: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add eval/datasets/c5_venues.jsonl eval/eval_c5.py eval/results-2026-06.json
git commit -m "eval(c5): venue watchlist calibration (IJISRT predatory vs reputable, 0 FP target)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Skill rubric update (scoring lives here, not in the tool)

**Files:**
- Modify: `skill/SKILL.md` (Mode C C5 rubric rows + decisive-red-flag anchoring note)
- Modify: `skill/references/integrity-signals.md` (C5 venue line)

- [ ] **Step 1: Update SKILL.md C5 scoring guidance**

Find the Mode C rubric (the table with `| C5 | 掠奪性/可疑出版 | 15 |`) and the "決定性紅旗錨定" line. Edit so:
- The C5 row references the deterministic flags: "venue_hijacked / venue_predatory (watchlist) + DOAJ/IF 佐證".
- The decisive-red-flag anchoring sentence adds `venue_hijacked` to the list that anchors to 🔴 (alongside confirmed retraction / AI-residue / mass-hallucinated-refs).
- Add a sub-bullet under the C5 description: "`venue_predatory`(Beall's 期刊/出版社命中)→ 填滿 C5(amber 線索,非自動 🔴,清單有爭議);`venue_hijacked`(劫持/克隆期刊)→ 決定性 🔴;單純 `not_in_doaj_journal` → advisory(正規訂閱期刊也會中),不單獨升級。卷宗須引用 watchlist 來源 + snapshot_date,並註明清單命中是線索非定論。"

Show the exact edited lines in the commit. Keep wording in Traditional Chinese to match the file.

- [ ] **Step 2: Update integrity-signals.md C5 line**

Change the "Venue legitimacy" bullet to mention the deterministic watchlists first, DOAJ/IF as secondary:

```
- Venue legitimacy (deterministic first): paper-verify flags `venue_hijacked` (clone/hijacked journal → decisive red) and `venue_predatory` (Beall's standalone journal or publisher → amber lead) from a bundled, dated watchlist (data/watchlists.json; refresh via build_watchlists.py). DOAJ membership and fake-impact-factor checks are secondary corroboration — `not_in_doaj_journal` alone is advisory (reputable subscription journals trip it too). Beall's List is contested; a hit is a lead, not a verdict.
```

- [ ] **Step 3: Sanity check the skill files render (no broken table)**

Run: `cd /d/paper/hype_experiment_3/repo && grep -n "venue_hijacked\|venue_predatory\|C5" skill/SKILL.md skill/references/integrity-signals.md`
Expected: the new terms present in both files; the rubric table still has its pipe structure intact.

- [ ] **Step 4: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/SKILL.md skill/references/integrity-signals.md
git commit -m "docs(skill): C5 rubric uses watchlist flags (hijacked decisive, predatory amber, DOAJ advisory)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Sync to live skill + final verification

**Files:**
- Copy: `skill/paper-verify/verify.py` + `skill/paper-verify/data/watchlists.json` → live skill dir
- Copy: `skill/SKILL.md` C5 edits + `skill/references/integrity-signals.md` → live (these are content files; copy is fine — but the LIVE SKILL.md keeps its own absolute paths, so apply the SAME C5 text edits to the live SKILL.md rather than overwriting the whole file).

- [ ] **Step 1: Sync the tool + data (whole-file copy is safe for these)**

```bash
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/verify.py \
   "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/verify.py"
mkdir -p "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/data"
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/data/watchlists.json \
   "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/data/watchlists.json"
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/build_watchlists.py \
   "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/build_watchlists.py"
```

- [ ] **Step 2: Verify live tool works with the data file present**

Run:
```bash
cd "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify"
python -c "import verify; wl=verify.load_watchlists(); print('issn_entries', len(wl['issn'])); print(verify.match_venue({'name':'X','issn':['2456-2156']}, wl))"
```
Expected: `issn_entries` ≥ 1 and a predatory hit dict printed (confirms the live tool finds its data file via `DEFAULT_WATCHLISTS`).

- [ ] **Step 3: Apply the C5 text edits to the LIVE SKILL.md (targeted, not whole-file)**

Open the live `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\SKILL.md`, find the same C5 rubric lines as Task 7 Step 1, and apply the SAME Traditional-Chinese edits. Do NOT copy the repo SKILL.md over it (the live file has its own absolute paths). Same for the live `references/integrity-signals.md` (this one has no absolute paths → whole-file copy is acceptable):

```bash
cp /d/paper/hype_experiment_3/repo/skill/references/integrity-signals.md \
   "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/references/integrity-signals.md"
```

- [ ] **Step 4: Full unit suite green + quick smoke**

```bash
cd /d/paper/hype_experiment_3/repo/skill/paper-verify && python -m pytest -m "not integration" -q
```
Expected: all unit tests pass.

- [ ] **Step 5: Final commit (local only — do NOT push)**

```bash
cd /d/paper/hype_experiment_3/repo
git add -A
git commit -m "chore(paper-verify): C5 watchlist feature complete; live skill synced

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git log --oneline -8
```

Report: unit count, eval_c5 FP rate, that live `match_venue` returned a predatory hit, and that nothing was pushed.

---

## Notes for the executor

- **Honesty gates:** if `eval_c5` shows any FP on a reputable journal, fix the data/matcher before recording numbers — do not ship a watchlist that re-creates the BMJ problem. If `build_watchlists.py` parsers produce noise, keep the curated seed and say so. A watchlist hit is a *lead*, surfaced for the reader — never phrased as an accusation.
- **Do not change `verify()`'s return shape** beyond the additive `venue.watchlist` key and the two new flags.
- **Push is gated:** everything stays local until the user explicitly says "push".
