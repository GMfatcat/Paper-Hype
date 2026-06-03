# paper-verify (API backbone) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, Dockerized `paper-verify` CLI that resolves a paper via OpenAlex + ORCID and prints a JSON of facts + boolean red-flags for checks C1/C4/C5 + author identity, then wire it into the skill's Mode C/B verification.

**Architecture:** Pure functions (`extract_facts`, `compute_flags`, `build_openalex_url`) hold all logic and are unit-tested with inline fixtures (no network). Network functions (`fetch_openalex`, `fetch_orcid_exists`, `enrich_authors`) are thin and dependency-injected into `verify()`, so orchestration is tested without network; a few real-DOI integration smokes confirm the live wiring. Stdlib `urllib` only — no pip deps.

**Tech Stack:** Python 3.11 (stdlib only: `urllib`, `json`), pytest (dev), Docker (`python:3.11-slim`).

**Spec:** `docs/design/2026-06-03-paper-verify-api-backbone-design.md`

**Where to build:** in the repo at `repo/skill/paper-verify/` (git + pytest work here). The skill is mirrored at `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\`; Task 9 syncs the tool dir + the 3 markdown edits to the live skill. Commits are local (no push) unless the user says otherwise.

**Run tests from:** `repo/skill/paper-verify/` → `pytest -v` (unit, no network). Integration smokes: `pytest -v -m integration` (network).

---

## File Structure
| File | Responsibility |
|---|---|
| `repo/skill/paper-verify/verify.py` | tool: pure logic + thin network layer + CLI |
| `repo/skill/paper-verify/test_verify.py` | pytest: unit (inline fixtures) + integration smokes |
| `repo/skill/paper-verify/Dockerfile` | container (`python:3.11-slim`, stdlib only) |
| `repo/skill/paper-verify/README.md` | usage, JSON shape, honesty notes, limits |
| `repo/skill/references/templates.md` | Template F: call paper-verify first, fall back to WebFetch |
| `repo/skill/references/integrity-signals.md` | add OpenAlex/ORCID endpoints |
| `repo/skill/SKILL.md` | Mode C 取文 step: invoke paper-verify |

Constants (defined once in verify.py, used across tasks): `OPENALEX="https://api.openalex.org"`, `MAILTO="paper-verify@example.org"`, `MIN_AUTHORS=5`, `WEAK_RATIO=0.6`, `WEAK_WORKS=1`.

---

## Task 1: `build_openalex_url()` — identifier → API URL

**Files:** Create `repo/skill/paper-verify/verify.py`, `repo/skill/paper-verify/test_verify.py`

- [ ] **Step 1: Write the failing test**
```python
# test_verify.py
import verify

def test_build_url_doi():
    u = verify.build_openalex_url("10.1126/science.adi2336")
    assert u.startswith("https://api.openalex.org/works/https://doi.org/10.1126/science.adi2336")
    assert "mailto=" in u

def test_build_url_doi_full_link():
    u = verify.build_openalex_url("https://doi.org/10.1016/S0140-6736(20)31180-6")
    assert "/works/https://doi.org/10.1016/S0140-6736(20)31180-6" in u

def test_build_url_arxiv():
    assert "/works/arxiv:2212.12794" in verify.build_openalex_url("arXiv:2212.12794")
    assert "/works/arxiv:2606.02437" in verify.build_openalex_url("2606.02437")

def test_build_url_title_search():
    u = verify.build_openalex_url("Attention Is All You Need")
    assert "/works?search=Attention" in u and "per_page=1" in u
```

- [ ] **Step 2: Run test, verify it fails**
Run: `pytest test_verify.py -v`
Expected: FAIL (module/function not found).

- [ ] **Step 3: Implement**
```python
# verify.py
import json
import sys
import urllib.parse
import urllib.request

OPENALEX = "https://api.openalex.org"
MAILTO = "paper-verify@example.org"
MIN_AUTHORS = 5
WEAK_RATIO = 0.6
WEAK_WORKS = 1


def build_openalex_url(identifier):
    ident = (identifier or "").strip()
    low = ident.lower()
    if low.startswith("10.") or "doi.org/" in low:
        doi = ident.split("doi.org/")[-1]
        return f"{OPENALEX}/works/https://doi.org/{doi}?mailto={MAILTO}"
    arx = low.replace("arxiv:", "").strip()
    if len(arx) >= 9 and arx[:4].isdigit() and "." in arx and "/" not in arx and " " not in arx:
        return f"{OPENALEX}/works/arxiv:{arx}?mailto={MAILTO}"
    q = urllib.parse.quote(ident)
    return f"{OPENALEX}/works?search={q}&per_page=1&mailto={MAILTO}"
```

- [ ] **Step 4: Run test, verify it passes** — Run: `pytest test_verify.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
cd repo/skill/paper-verify
git add verify.py test_verify.py
git commit -m "feat(paper-verify): identifier->OpenAlex URL builder"
```

---

## Task 2: `extract_facts()` — OpenAlex work → facts dict

**Files:** Modify `verify.py`, `test_verify.py`

- [ ] **Step 1: Write the failing test**
```python
CLEAN_WORK = {
    "id": "https://openalex.org/W123",
    "title": "GraphCast",
    "is_retracted": False,
    "cited_by_count": 1051,
    "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    "primary_location": {"source": {
        "display_name": "Science", "type": "journal", "is_in_doaj": False,
        "host_organization_name": "AAAS", "issn": ["0036-8075"]}},
    "authorships": [
        {"author": {"display_name": "Remi Lam", "orcid": "https://orcid.org/0000-0001-0000-0001"},
         "institutions": [{"display_name": "DeepMind"}]},
        {"author": {"display_name": "A. N. Other", "orcid": None}, "institutions": []},
    ],
}

def test_extract_facts_basic():
    f = verify.extract_facts(CLEAN_WORK)
    assert f["title"] == "GraphCast"
    assert f["retraction"]["is_retracted"] is False
    assert f["venue"]["name"] == "Science"
    assert f["venue"]["type"] == "journal"
    assert f["venue"]["is_in_doaj"] is False
    assert f["references"]["referenced_works_count"] == 2
    assert f["references"]["cited_by_count"] == 1051
    assert f["authors"][0]["orcid"] == "0000-0001-0000-0001"
    assert f["authors"][0]["institution"] == "DeepMind"
    assert f["authors"][1]["orcid"] is None
```

- [ ] **Step 2: Run test, verify it fails** — Run: `pytest test_verify.py::test_extract_facts_basic -v` → FAIL.

- [ ] **Step 3: Implement (append to verify.py)**
```python
def extract_facts(work):
    src = ((work.get("primary_location") or {}).get("source")) or {}
    authors = []
    for a in work.get("authorships", []):
        au = a.get("author") or {}
        orcid = au.get("orcid")
        insts = a.get("institutions") or []
        authors.append({
            "name": au.get("display_name"),
            "orcid": orcid.replace("https://orcid.org/", "") if orcid else None,
            "orcid_verified": None,           # filled by enrich_authors (network)
            "works_count": None,              # filled by enrich_authors for no-ORCID authors
            "openalex_author_id": au.get("id"),
            "institution": insts[0].get("display_name") if insts else None,
        })
    return {
        "openalex_id": work.get("id"),
        "title": work.get("title") or work.get("display_name"),
        "retraction": {"is_retracted": bool(work.get("is_retracted")), "note": ""},
        "venue": {
            "name": src.get("display_name"),
            "type": src.get("type"),
            "is_in_doaj": src.get("is_in_doaj"),
            "publisher": src.get("host_organization_name"),
            "issn": src.get("issn") or [],
        },
        "authors": authors,
        "references": {
            "referenced_works_count": len(work.get("referenced_works") or []),
            "cited_by_count": work.get("cited_by_count"),
            "provided_checked": 0,
            "provided_unresolved": [],
        },
    }
```

- [ ] **Step 4: Run test, verify it passes** — `pytest test_verify.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add verify.py test_verify.py
git commit -m "feat(paper-verify): extract_facts from OpenAlex work"
```

---

## Task 3: `compute_flags()` — facts → boolean red-flags

**Files:** Modify `verify.py`, `test_verify.py`

- [ ] **Step 1: Write the failing test**
```python
def _facts(authors=None, is_retracted=False, vtype="journal", in_doaj=True):
    return {
        "retraction": {"is_retracted": is_retracted, "note": ""},
        "venue": {"type": vtype, "is_in_doaj": in_doaj, "publisher": "X"},
        "authors": authors if authors is not None else [
            {"orcid": "0000-1", "works_count": 30}, {"orcid": "0000-2", "works_count": 5}],
        "references": {"provided_unresolved": []},
    }

def test_flag_retracted():
    assert verify.compute_flags(_facts(is_retracted=True))["retracted"] is True

def test_flag_not_in_doaj_journal():
    assert verify.compute_flags(_facts(in_doaj=False))["not_in_doaj_journal"] is True

def test_flag_repo_only():
    assert verify.compute_flags(_facts(vtype="repository"))["venue_repository_only"] is True

def test_flag_author_identity_weak():
    weak = [{"orcid": None, "works_count": 0} for _ in range(5)] + [{"orcid": "0000-9", "works_count": 12}]
    fl = verify.compute_flags(_facts(authors=weak))
    assert fl["author_identity_weak"] is True
    assert fl["author_weak_ratio"] >= 0.6

def test_flag_clean_all_false():
    fl = verify.compute_flags(_facts())
    assert not any([fl["retracted"], fl["not_in_doaj_journal"], fl["author_identity_weak"]])

def test_flag_small_team_not_weak():
    # 2 no-ORCID authors but team < MIN_AUTHORS -> not flagged
    fl = verify.compute_flags(_facts(authors=[{"orcid": None, "works_count": 0},
                                              {"orcid": None, "works_count": 0}]))
    assert fl["author_identity_weak"] is False
```

- [ ] **Step 2: Run test, verify it fails** — `pytest test_verify.py -k flag -v` → FAIL.

- [ ] **Step 3: Implement (append to verify.py)**
```python
def compute_flags(facts):
    authors = facts.get("authors") or []
    n = len(authors)
    def weak(a):
        wc = a.get("works_count")
        return (not a.get("orcid")) and (wc is None or wc <= WEAK_WORKS)
    weak_n = sum(1 for a in authors if weak(a))
    ratio = (weak_n / n) if n else 0.0
    venue = facts.get("venue") or {}
    vtype = venue.get("type")
    return {
        "retracted": bool(facts.get("retraction", {}).get("is_retracted")),
        "not_in_doaj_journal": vtype == "journal" and venue.get("is_in_doaj") is False,
        "venue_repository_only": vtype == "repository",
        "author_identity_weak": n >= MIN_AUTHORS and ratio >= WEAK_RATIO,
        "author_weak_ratio": round(ratio, 2),
        "work_not_found": False,
        "refs_unresolved": len(facts.get("references", {}).get("provided_unresolved") or []),
    }
```

- [ ] **Step 4: Run test, verify it passes** — `pytest test_verify.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add verify.py test_verify.py
git commit -m "feat(paper-verify): compute_flags with author-identity threshold"
```

---

## Task 4: network layer — `http_get_json`, `fetch_openalex`, `fetch_orcid_exists`, `enrich_authors`

**Files:** Modify `verify.py`, `test_verify.py`

- [ ] **Step 1: Write the failing test** (no real network — inject a fake fetcher)
```python
def test_fetch_openalex_unwraps_search(monkeypatch):
    # search responses have {"results": [...]}; single-work responses don't
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"results": [{"id": "W1"}]})
    assert verify.fetch_openalex("some title")["id"] == "W1"
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"id": "W2"})
    assert verify.fetch_openalex("10.1/x")["id"] == "W2"

def test_fetch_openalex_returns_none_on_error(monkeypatch):
    def boom(url, timeout=30):
        raise RuntimeError("404")
    monkeypatch.setattr(verify, "http_get_json", boom)
    assert verify.fetch_openalex("10.1/x") is None

def test_fetch_openalex_empty_search(monkeypatch):
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"results": []})
    assert verify.fetch_openalex("no such title") is None
```

- [ ] **Step 2: Run test, verify it fails** — `pytest test_verify.py -k fetch -v` → FAIL.

- [ ] **Step 3: Implement (append to verify.py)**
```python
def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify (mailto:{MAILTO})",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_openalex(identifier):
    try:
        data = http_get_json(build_openalex_url(identifier))
    except Exception:
        return None
    if isinstance(data, dict) and "results" in data:
        results = data.get("results") or []
        return results[0] if results else None
    return data


def fetch_orcid_exists(orcid, timeout=20):
    if not orcid:
        return False
    oid = orcid.rstrip("/").split("/")[-1]
    try:
        req = urllib.request.Request(f"https://pub.orcid.org/v3.0/{oid}/person",
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def enrich_authors(authors):
    # confirm ORCIDs; for no-ORCID authors fetch works_count via /authors/{id}
    for a in authors:
        if a.get("orcid"):
            a["orcid_verified"] = fetch_orcid_exists(a["orcid"])
        elif a.get("openalex_author_id"):
            try:
                au = http_get_json(f"{a['openalex_author_id']}?mailto={MAILTO}")
                a["works_count"] = au.get("works_count")
            except Exception:
                a["works_count"] = None
    return authors
```

- [ ] **Step 4: Run test, verify it passes** — `pytest test_verify.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add verify.py test_verify.py
git commit -m "feat(paper-verify): network layer (OpenAlex/ORCID) with injectable http"
```

---

## Task 5: `verify()` orchestration + `work_not_found` fallback

**Files:** Modify `verify.py`, `test_verify.py`

- [ ] **Step 1: Write the failing test**
```python
def test_verify_not_found(monkeypatch):
    monkeypatch.setattr(verify, "fetch_openalex", lambda i: None)
    r = verify.verify("2606.99999")
    assert r["resolved"] is False
    assert r["flags"]["work_not_found"] is True
    assert "too new" in " ".join(r["notes"]).lower() or "not" in " ".join(r["notes"]).lower()

def test_verify_resolved(monkeypatch):
    monkeypatch.setattr(verify, "fetch_openalex", lambda i: CLEAN_WORK)
    monkeypatch.setattr(verify, "enrich_authors", lambda authors: authors)  # skip network
    r = verify.verify("10.1126/science.adi2336")
    assert r["resolved"] is True
    assert r["title"] == "GraphCast"
    assert r["flags"]["retracted"] is False
    assert "openalex" in " ".join(r["notes"]).lower()
```

- [ ] **Step 2: Run test, verify it fails** — `pytest test_verify.py -k verify_ -v` → FAIL.

- [ ] **Step 3: Implement (append to verify.py)**
```python
def verify(identifier):
    work = fetch_openalex(identifier)
    if work is None:
        return {
            "query": identifier, "resolved": False, "openalex_id": None, "title": None,
            "retraction": {"is_retracted": False, "note": ""}, "venue": {}, "authors": [],
            "references": {"referenced_works_count": None, "cited_by_count": None,
                           "provided_checked": 0, "provided_unresolved": []},
            "flags": {"retracted": False, "not_in_doaj_journal": False,
                      "venue_repository_only": False, "author_identity_weak": False,
                      "author_weak_ratio": 0.0, "work_not_found": True, "refs_unresolved": 0},
            "notes": ["not found in OpenAlex — likely too new / not yet indexed; fall back to WebFetch checks"],
        }
    facts = extract_facts(work)
    facts["authors"] = enrich_authors(facts["authors"])
    flags = compute_flags(facts)
    result = {"query": identifier, "resolved": True}
    result.update(facts)
    result["flags"] = flags
    result["notes"] = ["resolved via OpenAlex"]
    return result
```

- [ ] **Step 4: Run test, verify it passes** — `pytest test_verify.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add verify.py test_verify.py
git commit -m "feat(paper-verify): verify() orchestration + not-found fallback"
```

---

## Task 6: CLI entrypoint + integration smokes (real network)

**Files:** Modify `verify.py`, `test_verify.py`

- [ ] **Step 1: Write the failing tests**
```python
import json as _json, subprocess, sys, pytest

def test_cli_outputs_json(monkeypatch):
    # format_output must produce parseable JSON with required keys
    r = {"query": "x", "resolved": False, "flags": {"work_not_found": True}, "notes": []}
    out = verify.format_output(r)
    parsed = _json.loads(out)
    assert parsed["resolved"] is False

@pytest.mark.integration
def test_integration_retracted():
    r = verify.verify("10.1016/S0140-6736(20)31180-6")  # Surgisphere/Lancet, retracted
    assert r["resolved"] is True
    assert r["flags"]["retracted"] is True

@pytest.mark.integration
def test_integration_clean():
    r = verify.verify("10.1126/science.adi2336")  # GraphCast
    assert r["resolved"] is True
    assert r["flags"]["retracted"] is False
    assert r["venue"]["name"]  # has a venue
```

- [ ] **Step 2: Run unit test, verify it fails** — `pytest test_verify.py::test_cli_outputs_json -v` → FAIL (no format_output).

- [ ] **Step 3: Implement (append to verify.py)**
```python
def format_output(result):
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"resolved": False, "notes": ["usage: python verify.py <DOI|arXiv id|title>"]}))
        sys.exit(0)
    print(format_output(verify(sys.argv[1])))
```
Also create `repo/skill/paper-verify/pytest.ini`:
```ini
[pytest]
markers =
    integration: hits live OpenAlex/ORCID APIs (network)
```

- [ ] **Step 4: Verify** — `pytest test_verify.py -v` (unit PASS; integration skipped by default unless `-m integration`). Then run the network smokes: `pytest -m integration -v` → both PASS. If OpenAlex is briefly unreachable, re-run; do not weaken assertions.

- [ ] **Step 5: Commit**
```bash
git add verify.py test_verify.py pytest.ini
git commit -m "feat(paper-verify): CLI entrypoint + integration smokes"
```

---

## Task 7: Dockerfile + README

**Files:** Create `repo/skill/paper-verify/Dockerfile`, `repo/skill/paper-verify/README.md`

- [ ] **Step 1: Write the Dockerfile**
```dockerfile
# build: docker build -t paper-verify .   (run from this dir)
# run:   docker run --rm paper-verify "<DOI|arXiv id|title>"
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
COPY verify.py /app/verify.py
WORKDIR /app
ENTRYPOINT ["python", "verify.py"]
```

- [ ] **Step 2: Build and smoke-test the image**
Run:
```bash
cd repo/skill/paper-verify
docker build -t paper-verify .
docker run --rm paper-verify "10.1016/S0140-6736(20)31180-6"
```
Expected: JSON with `"resolved": true` and `"retracted": true`.
Also run `docker run --rm paper-verify "10.1126/science.adi2336"` → `"retracted": false`, a venue name present.

- [ ] **Step 3: Write README.md**
```markdown
# paper-verify — structured-API verification (Mode C/B backbone)

Resolves a paper via **OpenAlex + ORCID** and prints facts + boolean red-flags. Deterministic, no API keys.

## Build & run
    cd skill/paper-verify
    docker build -t paper-verify .
    docker run --rm paper-verify "<DOI | arXiv id | title>"
(Or locally: `python verify.py "<id>"` — stdlib only, no pip install.)

## Output (JSON)
`resolved`, `title`, `retraction.is_retracted`, `venue{name,type,is_in_doaj,publisher,issn}`,
`authors[]{name,orcid,orcid_verified,works_count,institution}`,
`references{referenced_works_count,cited_by_count}`,
`flags{retracted, not_in_doaj_journal, venue_repository_only, author_identity_weak, author_weak_ratio, work_not_found, refs_unresolved}`, `notes`.

## How the skill uses it
Mode C 取文/拆解 calls it once; C1/C4/C5 + author identity read its `facts+flags`. Scoring stays in the Mode C rubric (e.g. `retracted` → 🔴 anchor).

## Honesty / limits (v1)
- **`work_not_found` ≠ fraud.** New arXiv papers (days old) are often not yet indexed → `resolved:false`; the skill **falls back to WebFetch checks**.
- **No ORCID ≠ fake author.** Only aggregated (`author_weak_ratio`) is a weak signal; never a verdict on an individual.
- Not covered v1: C2/C3 (need full text, roadmap #2), deep hallucinated-ref check (needs `--refs` from #2), PubPeer/predatory lists.
- Politeness: OpenAlex polite pool via `mailto`; modest ORCID calls.
```

- [ ] **Step 4: Commit**
```bash
git add Dockerfile README.md
git commit -m "feat(paper-verify): Dockerfile + README"
```

---

## Task 8: Wire into the skill (Template F, integrity-signals, SKILL.md)

**Files:** Modify `repo/skill/references/templates.md`, `repo/skill/references/integrity-signals.md`, `repo/skill/SKILL.md`

- [ ] **Step 1: integrity-signals.md — add endpoints**
Append under the "Lookup endpoints" section:
```markdown
- Structured backbone (preferred, deterministic): `paper-verify` tool (skill/paper-verify/) → OpenAlex `https://api.openalex.org/works/<doi|arxiv:id>` + ORCID `https://pub.orcid.org/v3.0/<id>/person`. Use it first; fall back to the manual lookups above when it returns `resolved:false`.
```

- [ ] **Step 2: Template F — prepend the tool-first instruction**
In `templates.md`, in the Template F block, add a line right after the 共同前綴 paragraph:
```markdown
**優先**:先對該論文跑 `paper-verify`(skill/paper-verify/)取得 facts+flags;C1/C4/C5 直接採用其結果(`retracted`/`not_in_doaj_journal`/`author_identity_weak`/引用統計)。**僅當 `resolved:false`(常因太新未索引)才退回下列手動 WebFetch 查證**。C2/C3(AI 痕跡/tortured)仍走全文文字檢查。
```

- [ ] **Step 3: SKILL.md — Mode C 取文 step**
In the Mode C "取文" section, append a bullet:
```markdown
- **結構化事實**:先跑 `paper-verify "<DOI/arXiv/標題>"`(skill/paper-verify/,Docker 或 `python verify.py`)→ 拿 facts+flags 餵 C1/C4/C5 與作者識別;`resolved:false`(太新未索引)→ 退回 WebFetch,**不當紅旗**。
```

- [ ] **Step 4: Verify** — `grep -n "paper-verify" repo/skill/SKILL.md repo/skill/references/templates.md repo/skill/references/integrity-signals.md` shows all three updated.

- [ ] **Step 5: Commit**
```bash
git add repo/skill/SKILL.md repo/skill/references/templates.md repo/skill/references/integrity-signals.md
git commit -m "feat(mode-c): wire paper-verify into取文 + Template F + signals"
```

---

## Task 9: Sync to live skill + final commit

**Files:** copy tool dir + apply the 3 markdown edits to the live skill at `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\`

- [ ] **Step 1: Copy the tool dir to live**
```bash
mkdir -p "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify"
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/verify.py /d/paper/hype_experiment_3/repo/skill/paper-verify/Dockerfile /d/paper/hype_experiment_3/repo/skill/paper-verify/README.md "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/"
```
(Tests/pytest.ini stay in the repo only — not needed in the installed skill.)

- [ ] **Step 2: Apply the same 3 markdown edits to the live skill**
Re-apply the exact edits from Task 8 Steps 1–3 to the live copies: `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\references\integrity-signals.md`, `...\references\templates.md`, `...\SKILL.md`. (Same anchor strings; do NOT whole-file copy — that would clobber the live Mode B absolute paths which legitimately differ from the repo.)

- [ ] **Step 3: Verify live** — `grep -rn "paper-verify" "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/SKILL.md"` and confirm `verify.py` exists in the live `paper-verify/` dir.

- [ ] **Step 4: Final commit (repo, local; do NOT push unless user says)**
```bash
cd /d/paper/hype_experiment_3/repo
git add -A
git commit -m "chore(paper-verify): sync tool + skill wiring (local)"
git log --oneline -1
```

---

## Self-Review
- **Spec coverage:** §2 form→T1/T6/T7; §3 sources→T4; §4 pipeline→T2/T4/T5; §5 flags→T3 (all 7 flags incl. author_weak_ratio, work_not_found, refs_unresolved); §6 output JSON→T5/T6 (`verify()`/`format_output`); §7 honesty (not-found≠fraud, no-ORCID≠fake)→T5 not-found branch + T3 threshold + README; §8 integration→T8; §9 files→all; §10 testing→unit T1–T5 + integration T6 (clean/retracted; predatory & Mind Lab covered by unit fixtures for flag logic + run manually once indexed); §11 roadmap (`--refs` reserved)→noted, not built in v1.
- **Placeholder scan:** none — every step has real code/commands. `--refs` is explicitly out of v1 per spec, not a placeholder.
- **Type/name consistency:** `build_openalex_url`, `http_get_json`, `fetch_openalex`, `fetch_orcid_exists`, `enrich_authors`, `extract_facts`, `compute_flags`, `verify`, `format_output` used consistently; flag keys identical between T3 `compute_flags`, T5 not-found branch, and README; constants `MIN_AUTHORS/WEAK_RATIO/WEAK_WORKS` defined once in T1.
- **Note:** the "too new / not indexed" reality (most of the 2026-06 batch) is covered by `work_not_found` → fallback, tested in T5.
