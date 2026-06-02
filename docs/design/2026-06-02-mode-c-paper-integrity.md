# Design Spec — Mode C: Paper Integrity Triage（論文採信風險快篩）

- **Date:** 2026-06-02
- **Status:** Design approved; pending implementation plan
- **Adds to skill:** `dissecting-paper-hype` (new third mode alongside Mode A study / Mode B post quick-check)
- **One-line:** Given a paper link, produce a private *trust-risk* score + evidence dossier so a reader can decide whether to trust / cite / build on it.

---

## 1. Purpose & framing

Mode B judges a **marketing post**; Mode C judges the **paper itself**. The critical difference: a paper's authors are real, named people, so getting it wrong is an accusation that can damage careers and rebound on the accuser. Therefore Mode C is deliberately scoped to **reader self-defense**, not fraud-busting.

**Output is a private trust-risk assessment for the reader's own decision** — *should I trust / cite / follow this paper?* — **not** a fraud verdict, **not** material for a public call-out or a misconduct report (檢舉).

Hard principles (carried into the skill):
- Every red flag is a **verifiable lead with provenance + a confidence level**, framed as "needs human judgment," never as proof of misconduct.
- **查不到 ≠ 造假** — absence of evidence is not evidence of fabrication.
- A clean score ≠ "the paper is correct or good"; it only means "no automated integrity red flags were found."
- **Never assert a fact about the paper or a reference from memory** — it must be verified by an actual lookup (the same discipline as Mode B).

## 2. Scope

**In scope (v1):** single paper, fed by link, scored on five high-signal, fully-automatable checks (below).

**Out of scope (v1):**
- Public naming / call-out content, or auto-submitting misconduct reports → the ethics gate refuses and redirects to self-defense use.
- **Image forensics** (duplicated/spliced blots, gels) → flag as "needs a specialized tool (ImageTwin/Proofig)"; do not attempt a verdict.
- **Large-corpus plagiarism matching** → out; may be a future "提示 only" addition.
- Statistical sanity tests (GRIM/statcheck) → deferred to a possible v2 (needs reliable number extraction from full text).

## 3. Trigger & routing

Add Mode C to the skill's mode router. Triggers: user supplies a paper (arXiv / DOI / publisher URL) and asks about its trustworthiness/integrity — e.g. "這篇可信嗎"、"有沒有造假/問題"、"該不該引用這篇"、"is this paper legit / trustworthy".

Ethics gate (Mode C specific): if the intent is to produce a public accusation or a formal report naming individuals, stop and explain Mode C is self-defense triage only.

## 4. Input / fetch (reuse + extend the fetch adapter)

Link → fetch **metadata + abstract + full text + reference list**.
- arXiv / open-access: full text available (HTML/PDF) → full check.
- Paywalled: often only abstract + references → **mark "full-text unavailable → limited check," lower confidence, proceed** with what is available. Never score a partial fetch as if complete.

## 5. Pipeline

1. **Fetch** (§4).
2. **Extract:** reference list; full-text body (for AI-trace & tortured-phrase scans); venue/journal name + DOI; author names.
3. **Verify — five checks, dispatched as parallel sub-agents** (§6).
4. **Aggregate:** weighted trust-risk score (§7) + dossier; each finding carries evidence, provenance, confidence, and "what to verify yourself."
5. **Report** (§8).

## 6. The five checks (v1)

| ID | Check | Method | Why it's high-signal |
|----|-------|--------|----------------------|
| **C1** | Hallucinated / nonexistent references | For each reference (sample + disclose if very many), confirm it resolves via Crossref / DOI / arXiv and that title–author–year match a real record. Distinguish "confirmed nonexistent" from "could not verify." | Fabricated citations are a top tell of AI-generated or fraudulent papers. |
| **C2** | AI-generation traces | Scan full text for literal artifacts: "As an AI language model", "Certainly, here is", "Regenerate response", "as of my last knowledge update", "I cannot provide", etc. | Smoking-gun when literal model strings survive into the published text. |
| **C3** | Tortured phrases | Match against known paper-mill paraphrase fingerprints (e.g. "colossal information" = big data), per the Problematic Paper Screener list. | Strong fingerprint of plagiarism-by-paraphrase / paper mills. |
| **C4** | Retraction / PubPeer status | Search Retraction Watch + PubPeer for the DOI/title and the authors. | The paper or its authors may already be community- or publisher-flagged. |
| **C5** | Predatory / suspect venue | Check venue against DOAJ and known predatory / hijacked-journal indicators; detect fake-impact-factor claims. | Venue legitimacy is a fast, objective trust signal. |

## 7. Scoring model — trust-risk 0–100 (higher = more caution warranted)

This is **"your-trust risk," not a fraud probability.** Draft per-check caps (final combination formula to be fixed in the plan; caps may overlap, then normalize to 100):

| Check | Max contribution |
|-------|------------------|
| C1 hallucinated refs | 30 |
| C2 AI-generation traces | 25 |
| C4 retraction / PubPeer | 25 |
| C5 predatory venue | 15 |
| C3 tortured phrases | 15 |

**Bands:**
- **0–20 🟢** no major flags
- **21–45 🟡** minor — verify yourself
- **46–70 🟠** several flags — be skeptical
- **71–100 🔴** serious integrity flags — do not rely on without independent verification

Coverage adjustment: when full text is unavailable, checks needing full text (C1 full list, C2, C3) are partial — report reduced **coverage/confidence** rather than silently treating them as passed.

## 8. Output / report format (Template G)

- **Trust-risk score + band + one-line bottom line** (trust / verify-more / be-skeptical).
- **Per-check findings table:** check · result · evidence (quoted/located) · provenance (URL) · confidence · "what to verify yourself."
- **Coverage disclosure:** was full text obtained? how many references were checked vs sampled?
- **Recommended next step** for the reader (e.g. "read PubPeer thread X", "these 3 cited papers could not be found — confirm them before citing").
- Standard disclaimer header: automated, heuristic, self-defense aid; clean ≠ correct; not a misconduct determination.

## 9. Error handling & honesty rules

- Full text unavailable → reduced coverage + lower confidence, stated explicitly.
- Huge reference list → sample N, **disclose the sampling** (no silent truncation).
- A source/tool unreachable → mark that check **"not run,"** never "passed."
- Never claim a reference is fake from memory — verify by lookup.
- Always distinguish "could not verify exists" from "confirmed nonexistent."

## 10. Reuse vs new components

**Reuse:** scrapling-fetcher (extend to return full text + reference list); the Mode B verification-sub-agent pattern; report-template style; the ethics gate; the "verify, don't trust memory" discipline.

**New:**
- `references/templates.md` → **Template F** (per-check integrity sub-agent prompts) and **Template G** (Mode C verdict report).
- A data file of **tortured-phrase patterns + AI-generation trace strings** (e.g. `references/integrity-signals.md`).
- The scoring weights/combination.
- SKILL.md: Mode C section + router entry + description update.

## 11. Testing plan (RED → GREEN, per writing-skills discipline)

Baseline (RED): without Mode C, a sub-agent scores a paper from memory and does not look up references / PubPeer — document that gap.

With Mode C (GREEN), verify it actually performs lookups and that:

| Test paper | Expected |
|------------|----------|
| A known **retracted** paper | C4 fires; 🟠/🔴; cites the retraction notice |
| A paper with **AI traces / tortured phrases** (from Problematic Paper Screener) | C2/C3 fire with quoted evidence |
| A **solid, reputable** paper | 🟢 — **must not be false-flagged** (the key anti-false-positive test) |
| A **paywalled** paper | graceful degradation: "limited check," reduced confidence, no overclaim |

## 12. Future (not v1)

Statistical sanity (GRIM/statcheck); image-forensics hand-off; plagiarism "提示 only"; author-level track-record view (kept cautious — edges toward profiling even in self-defense framing).
