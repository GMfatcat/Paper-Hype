# Design Spec — `pdf-extract`: full-text + reference extraction (方向 #2)

- **Date:** 2026-06-03
- **Status:** Design approved; pending implementation plan
- **Part of:** roadmap 1→2→4. This is **#2** (builds on #1 `paper-verify`). #4 = Mode B batch comes next.
- **Affects skill:** `dissecting-paper-hype` (Mode C — unlocks C2/C3 on real full text; completes C1 via `paper-verify --refs`).
- **One-line:** A deterministic, Dockerized `pdf-extract` tool that returns a paper's **full text + reference list** (arXiv HTML first, text-layer PDF second, no OCR), so Mode C's C2/C3 stop hitting "涵蓋受限" and C1 hallucinated-reference detection can finally run.

---

## 1. Problem & goal

In the 20-paper batch scan, "全文取不到 / 圖片化 PDF → 涵蓋受限" was the most common limitation: C2 (AI-residue strings) and C3 (tortured phrases) need full text, and C1 deep hallucinated-reference detection needs the bibliography. `paper-verify` (#1) gives API facts but **not** the paper's own text.

**Goal:** a deterministic tool that extracts full text + a reference list for a paper, prioritising the cleanest source. It feeds C2/C3 directly and feeds C1 by handing its reference list to `paper-verify --refs`.

**Non-goals (v1):** OCR (image/scanned PDFs), paywall bypass, table/formula/figure structuring, figure-image analysis (that's image-forensics, a separate track).

## 2. Form & placement

New Dockerized Python CLI at `skill/pdf-extract/` (Dockerfile + `extract.py` + README), a sibling of `paper-verify/` and `scrapling-fetcher/` — one tool, one job. Usage: `docker run --rm pdf-extract "<arXiv id | PDF URL>"` (or `python extract.py "<…>"`) → one JSON object on stdout; diagnostics to stderr.

## 3. Source priority (best → worst, fall through)

1. **arXiv** (id, or arxiv.org/abs|pdf URL) → fetch `https://arxiv.org/html/<id>` (official HTML full text) → parse clean body text + structured references. **Best path.**
2. **Other / arXiv-without-HTML** → fetch the PDF (URL) → **text-layer extraction via PyMuPDF**.
3. **Image/scanned PDF** (no text layer) → set `text_layer:false, coverage:"none"`; **do not OCR — fall back honestly** (Mode C keeps "涵蓋受限").
4. **Paywalled / unreachable** → `ok:false` with an explanatory note.

## 4. What it extracts

- **Full text** (plain) — for C2 (AI-residue strings) and C3 (tortured phrases) scanning.
- **Reference list** (array of strings):
  - arXiv HTML: use the structured bibliography (the `<ol>` / reference list items).
  - PDF text: locate the "References"/"Bibliography" heading, split the tail into entries by `[n]` markers / numbered patterns / blank-line heuristics.
  - **Heuristic and imperfect** → always report `references_count` and a confidence note; never claim completeness.

## 5. Output JSON (shape)

```json
{
  "query": "2312.00752",
  "ok": true,
  "source": "arxiv_html | pdf_textlayer | none",
  "coverage": "full | partial | none",
  "text_layer": true,
  "fulltext": "<plain text>",
  "fulltext_chars": 48213,
  "references": ["<ref1>", "<ref2>"],
  "references_count": 58,
  "notes": ["arXiv HTML used"]
}
```
- `coverage`: `full` (HTML or clean text layer), `partial` (got some but truncated/messy), `none` (no text layer / unreachable).
- On failure: `{"ok": false, "source": "none", "coverage": "none", "notes": ["..."]}`.

## 6. Integration into Mode C (composable, not chained)

- Mode C 取文: run **both** `paper-verify` (facts/flags) and `pdf-extract` (fulltext + references).
- **C2/C3**: scan `fulltext` directly → no longer routinely "涵蓋受限" (when source is arxiv_html/pdf_textlayer).
- **C1 (hallucinated refs)**: pipe `pdf-extract`'s `references` into `paper-verify --refs <list>` → `provided_unresolved` count → completes C1.
- `coverage:"none"` (image PDF) or `ok:false` → C2/C3 marked 受限 as today (honest degradation, no regression).
- Tools stay separate (pdf-extract does not call paper-verify itself) — composability over coupling.

## 7. Components / files

- **Create:** `skill/pdf-extract/{Dockerfile, extract.py, README.md}`
- **Modify:** `skill/SKILL.md` (Mode C 取文 step: add pdf-extract + C1-via-`--refs`), `skill/references/templates.md` (Template F C1: when references available, use `paper-verify --refs`).

## 8. Dependencies

- `PyMuPDF` (pip, no system libs — Docker-friendly) for PDF text-layer extraction.
- stdlib `urllib` for fetching arXiv HTML / PDF; lightweight HTML parsing (regex / `html.parser`) for the arXiv HTML body + references.
- **No tesseract / no OCR.**

## 9. Testing (RED→GREEN)

Pure functions (source detection from identifier; reference splitting from a text block; arXiv-HTML body/refs parsing from a fixture string) → deterministic unit tests with inline fixtures. Fetching → integration smokes.

| Case | Input | Expected |
|---|---|---|
| arXiv HTML | `2312.00752` (Mamba) | `source:"arxiv_html"`, `coverage:"full"`, fulltext contains "selective state space", `references_count > 0` |
| text-layer PDF | an open-access PDF URL with a text layer | `source:"pdf_textlayer"`, fulltext non-empty |
| image/scanned PDF | a known image-only PDF URL | `text_layer:false`, `coverage:"none"`, `ok:true`, honest note (no crash, no OCR) |
| unreachable/paywalled | a paywalled PDF URL | `ok:false`, explanatory note |
| end-to-end C1 | feed `references` from the Mamba run into `paper-verify --refs` | returns a `provided_unresolved` count |
| ref splitting (unit) | a fixture "References\n[1] A...\n[2] B..." block | returns 2 entries |

## 10. Roadmap linkage

- Completes the C1 path opened by #1 (`paper-verify --refs` was reserved for exactly this).
- #4 (Mode B batch) and Mode C batch both benefit: real full-text C2/C3 instead of degraded coverage.
- OCR remains a possible future add (would slot in as source step 2.5, image PDF → tesseract) without changing the interface.
