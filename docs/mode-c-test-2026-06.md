# Mode C end-to-end test — 20 fresh papers (2026-06)

A full run of the **Mode C (paper-integrity)** toolchain over **20 papers that
had never been tested before** (none appear in `eval/datasets/`, the example
batches, or any prior calibration run). Purpose: validate the post-C1-improvement
pipeline on real, fresh metadata and report honestly what fires, what doesn't,
and where the limits are.

**Reproduce:** `python eval/modec_run.py` (backbone) and
`python eval/modec_c1_run.py` (C1 subset). Raw output:
`eval/modec_results_2026-06.json`, `eval/modec_c1_results_2026-06.json`.

## Sample selection

- **10** fresh 2024 papers pulled live from OpenAlex (top-cited AI works with a
  DOI), spanning legit journals (Nucleic Acids Research, BMJ, Review of Economic
  Studies), conferences (CVPR, IEEE), a dataset re-deposit (CUB-200), and — by
  chance — **4 papers from IJISRT**, a journal on Beall's List.
- **7** flagship arXiv AI papers (BitNet, Mixtral, KAN, DeepSeek-R1, LoRA, QLoRA,
  FlashAttention).
- **3** deliberate edge cases: two **retracted** Nature papers (STAP cells,
  Obokata 2014) and **Llama 3** (very recent, an index-coverage probe).

## Backbone results (paper-verify facts + flags)

The deterministic backbone scores only tool-measurable signals (C4 retraction,
C5 DOAJ, repository venue, author identity). Qualitative C1/C2/C3/C5 are layered
separately (below).

| # | Paper | Light | Score | Resolved | Key flags |
|---|-------|-------|-------|----------|-----------|
| 1 | iTOL v6 (NAR) | 🟢 | 0 | ✓ | clean |
| 2 | TRIPOD+AI (BMJ) | 🟢 | 15 | ✓ | not_in_doaj |
| 3 | LLM agents survey (Frontiers CS) | 🟢 | 15 | ✓ | not_in_doaj |
| 4 | RT-DETR (CVPR 2024) | 🟢 | 0 | ✓ | clean |
| 5 | Event-Study Designs (Rev. Econ. Studies) | 🟢 | 15 | ✓ | not_in_doaj |
| 6 | Fault Detection ANN (IJISRT) | 🟢 | 15 | ✓ | not_in_doaj |
| 7 | Generative AI clinical docs (IJISRT) | 🟢 | 15 | ✓ | not_in_doaj |
| 8 | CUB-200-2011 dataset (CaltechAUTHORS) | 🟢 | 5 | ✓ | repository-only |
| 9 | YOLOv8 (IEEE conf) | 🟢 | 0 | ✓ | clean |
| 10 | MetaboAnalyst 6.0 (NAR) | 🟢 | 0 | ✓ | clean |
| 11 | BitNet b1.58 | 🟢 | 5 | ✓ | repository-only (arXiv) |
| 12 | Mixtral of Experts | 🟢 | 5 | ✓ | repository-only (arXiv) |
| 13 | KAN | 🟢 | 5 | ✓ | repository-only (arXiv) |
| 14 | DeepSeek-R1 | ⚪ | — | ✗ | not indexed → manual fallback |
| 15 | LoRA | 🟢 | 5 | ✓ | repository-only (arXiv) |
| 16 | QLoRA | 🟢 | 5 | ✓ | repository-only (arXiv) |
| 17 | FlashAttention | 🟢 | 5 | ✓ | repository-only (arXiv) |
| 18 | **STAP cells I (retracted)** | 🔴 | 95 | ✓ | **retracted** |
| 19 | **STAP cells II (retracted)** | 🔴 | 95 | ✓ | **retracted** |
| 20 | Llama 3 herd (very new) | ⚪ | — | ✗ | not indexed → manual fallback |

**Lights:** 🟢 16 · 🔴 2 · ⚪ 2.

## What the test validated

1. **C4 retraction → decisive red flag works.** Both STAP papers anchored to
   🔴 95 purely on `is_retracted=true`, not diluted by the rest of the record.
   This is the single most important Mode C signal and it fired cleanly.

2. **Index-coverage fallback is correct, not a red flag.** DeepSeek-R1 and
   Llama 3 are too recent for OpenAlex under their arXiv DOI → `resolved:false`
   → ⚪ GRAY "fall back to manual," exactly as the skill prescribes. A brand-new
   paper is *not* penalised as suspicious.

3. **Author-identity over-flagging stayed at zero.** No real team (industry or
   academic) tripped `author_identity_weak` — the earlier Mistral/Llama2
   false-positive fix holds on a fresh, author-heavy sample.

## Honest findings / limitations surfaced

### The DOAJ flag cannot tell predatory from reputable
`not_in_doaj_journal` fired identically (15 pts) on **BMJ** and **Review of
Economic Studies** (top-tier subscription journals) and on **IJISRT** (a Beall's
List journal). DOAJ only indexes open-access journals, so a reputable
subscription journal is "not in DOAJ" too. The flag is therefore a **weak,
non-discriminating signal** — which is why the rubric caps it at 15 pts (stays
🟢) and the real predatory determination is left to the **qualitative C5 check**.

Running that qualitative C5 by hand on the IJISRT papers confirms the gap:
IJISRT is **listed on Beall's List of predatory journals** (ISSN 2456-2156).
A complete Mode C run would escalate IJISRT via C5 (Beall's / hijacking / fake
impact-factor lookup), not via the DOAJ flag. **Takeaway:** keep the DOAJ flag
advisory; the predatory call requires the C5 subagent.

### C1 reference resolution has a high false-positive rate on messy refs
End-to-end C1 on three arXiv papers (extract refs → `resolve_refs`):

| Paper | refs | checked | unresolved | ratio | refs source |
|-------|------|---------|------------|-------|-------------|
| KAN | 118 | 40 | 5 | **0.125** | arxiv_html |
| BitNet | 28 | 28 | 14 | **0.50** | arxiv_html |
| LoRA | 62 | 40 | 22 | **0.55** | arxiv_html |

All three are legitimate papers, so **every "unresolved" here is a false
positive**. The driver is reference-string quality, not the resolver: BitNet's
unresolved refs are garbled by HTML extraction (prefixes like `CLC +`, `FAHA`,
`HCB +` and wrong `[n]` markers concatenated into the string), which defeats
Crossref `query.bibliographic`. KAN, whose extraction came out clean, sits at a
healthy 12.5%. This reproduces — on fresh real papers — the calibrated C1 FP
floor (~21% on the benchmark) and goes higher when extraction is dirty.

**Takeaways (both already in the skill, now empirically backed):**
- `refs_unresolved` is **advisory, never decisive** — the backbone correctly did
  *not* escalate any paper on unresolved refs. A 50% unresolved ratio on a real
  paper is an extraction artifact, not fraud.
- **Extraction quality is the lever, not resolver tuning.** Calibration already
  showed that loosening the matcher to cut FP crashes recall (0.82→0.45). The
  clean path forward is better references (run a **GROBID** service →
  `references_source: grobid`), which the skill already documents as raising C1
  confidence a level. KAN's clean-extraction result is the proof.

## Changes made

None to code. The test was a validation pass; its findings **confirm** the
existing design decisions (decisive-retraction anchor, advisory refs,
non-decisive DOAJ, GROBID as the C1-quality lever) rather than overturning them.
New artifacts: `eval/modec_run.py`, `eval/modec_c1_run.py`, and their JSON
outputs.
