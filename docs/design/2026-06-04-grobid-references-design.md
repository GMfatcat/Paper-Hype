# Design Spec — GROBID-backed reference extraction（補洞 A）

- **Date:** 2026-06-04
- **Status:** Design approved; pending implementation plan
- **Part of:** post-roadmap "borrow & patch" item **A** (from the 2026-06 competitive landscape). Patches the #2 weakness: best-effort reference extraction.
- **Affects:** `skill/pdf-extract/` (extract.py). No change to `paper-verify`.
- **One-line:** Add an optional GROBID (lite/CRF) reference-extraction path to `pdf-extract`; when a GROBID service is configured and reachable, use it for far better references (F1~0.9 vs the current regex's ~2/40), else fall back to the existing regex. Full-text extraction is unchanged.

---

## 1. Problem & goal

`pdf-extract`'s `split_references` is a regex heuristic that is weak on real PDFs (LLaMA: 2 of ~40 refs; Mamba arXiv-HTML: 0). This undercuts C1 (feeding references to `paper-verify --refs` for hallucinated-reference detection). GROBID is the open-source standard for PDF→structured references (F1~0.9).

**Goal:** when a GROBID service is available, `pdf-extract` returns high-quality references; when it isn't, behaviour is identical to today (regex). Full text path is untouched.

**Non-goals:** using GROBID for full text (keep arXiv-HTML/PyMuPDF); passing GROBID's structured fields directly to paper-verify (v1 still emits reference **strings** to preserve the `--refs` interface); building/bundling a GROBID image (use the official lite/CRF image); OCR.

## 2. GROBID service (optional, user-run)

- The user runs a **lite/CRF GROBID** container separately, e.g. `docker run -d --rm -p 8070:8070 <grobid-crf-image>` (exact image + RAM note in README; CRF image ~0.3–1 GB, modest RAM).
- `pdf-extract` reads env **`GROBID_URL`** (default `http://localhost:8070`). GROBID is used only when this endpoint is reachable.
- **Opt-in:** if `GROBID_URL` is unset/unreachable, `pdf-extract` runs exactly as today (stdlib-only + regex). GROBID is never required.

## 3. Changes to `extract.py`

New pure function + one network function + a decision change:
- `parse_grobid_tei(xml) -> [str]` (**pure**): parse GROBID TEI, extract each `<biblStruct>` into a reference string (concatenate authors + title + year + host/journal where present; fall back to the raw `<note type="raw_reference">` text if structured fields are sparse).
- `grobid_references(pdf_bytes, grobid_url) -> [str] | None` (network): POST the PDF to `<grobid_url>/api/processReferences` (multipart `input`), return `parse_grobid_tei(response)`; return `None` on any error/timeout (so caller can fall back).
- **Reference-acquisition decision order** (in `extract()` / `_extract_pdf`):
  1. arXiv HTML has structured bibliography (`ltx_bibitem`) → use it. `references_source = "arxiv_html"`.
  2. else (PDF path; or arXiv HTML with **0** refs, e.g. Mamba) → if `GROBID_URL` set & reachable → fetch the PDF bytes (arXiv: `arxiv.org/pdf/<id>`) → `grobid_references`. `references_source = "grobid"`.
  3. GROBID unset/unreachable/returns None → `split_references` (regex). `references_source = "regex_fallback"`.
- **Full-text path unchanged** (arXiv HTML / PyMuPDF as today).

## 4. Output JSON

Unchanged shape **plus** one field:
- `references`: array of strings (as today — feeds `paper-verify --refs` unchanged).
- **`references_source`**: `"arxiv_html" | "grobid" | "regex_fallback" | "none"` — transparency so Mode C / the reader knows how refs were obtained (and can weight C1 confidence: grobid > arxiv_html > regex_fallback).
- `notes`: include a line e.g. "references via GROBID" / "GROBID unreachable → regex fallback".

## 5. Dependency tradeoff (honest)

GROBID is an **opt-in heavy service** (separate container, Java). With it: reliable references → C1 works well. Without it: `pdf-extract` is unchanged (lightweight, best-effort regex). The README states plainly: run GROBID for good references; otherwise C1 stays best-effort.

## 6. Testing (RED→GREEN)

- **Unit (pure, no network/GROBID):** `parse_grobid_tei(TEI_FIXTURE)` — a small inline GROBID TEI `<biblStruct>` fixture (2–3 refs) → assert it returns those reference strings (authors/title/year joined). Include a `<note type="raw_reference">`-only entry to test the raw fallback.
- **Decision logic (injected fake grobid fetcher):** arXiv-HTML-with-refs → source `arxiv_html`; arXiv-HTML-0-refs + fake grobid returns refs → source `grobid`; grobid returns None → source `regex_fallback`. (No real network.)
- **Integration smokes (require a running GROBID):**
  - LLaMA `2302.13971` (PDF) → `references_source:"grobid"`, `references_count` ≫ 2 (target ~30–40) vs regex's 2.
  - Mamba `2312.00752` (arXiv HTML has no biblist) → GROBID-on-PDF rescues refs (count > 0).
  - GROBID stopped / `GROBID_URL` bogus → `references_source:"regex_fallback"`, no crash.
- **End-to-end:** GROBID refs → `paper-verify --refs` → resolved/unresolved counts.

## 7. Components / files

- **Modify:** `skill/pdf-extract/extract.py` (add `parse_grobid_tei`, `grobid_references`, decision order, `references_source`), `skill/pdf-extract/test_extract.py` (unit + decision tests; integration marked), `skill/pdf-extract/README.md` (how to run GROBID lite/CRF, `GROBID_URL`, opt-in behaviour, the `references_source` field).
- **Modify:** `skill/SKILL.md` Mode C 取文 note: references prefer GROBID (if running), else regex; mention `references_source` in the C1 confidence.
- **No change:** `paper-verify` (still consumes reference strings via `--refs`).
- **Optional (nice-to-have):** a `docker run` one-liner / compose snippet in `skill/pdf-extract/README.md` to start GROBID.

## 8. Rollout

Build in repo, unit + decision tests must pass with no GROBID present (proving opt-in/fallback). Integration smokes run once a GROBID container is started locally. Sync to live; local commits (no push until asked).
