# Design Spec — Mode B Batch（批量貼文快篩,方向 #4）

- **Date:** 2026-06-03
- **Status:** Design approved; pending implementation plan
- **Part of:** roadmap 1→2→4 — this is **#4**, the last step. Builds on Mode B + scrapling-fetcher + (for upgrades) paper-verify/pdf-extract.
- **Affects skill:** `dissecting-paper-hype` (adds a batch sub-flow to Mode B).
- **One-line:** Given a **user-supplied list** of posts (URLs and/or pasted texts), score each with a light first pass, rank them, and upgrade only the suspicious ones to a full single-post Mode B verdict — directly serving the original pain "Threads feed, few posts are actually worth reading."

---

## 1. Problem & goal

The user's original pain: scrolling Threads/X, most paper-sharing posts are hype and few are worth reading. Mode B judges one post; this batches it. Auto-enumerating a timeline is unreliable (JS infinite-scroll + login walls), so the batch is a **user-supplied set**. Two tiers keep cost down: cheap triage over all posts, deep verification only on the suspicious ones.

**Non-goals:** auto-scraping an account's timeline; cross-post author profiling / blocklists (stay self-defense, no profiling); producing public call-outs.

## 2. Trigger & input

Trigger: user supplies **a batch of posts** and asks to filter/rank them (e.g. "幫我一次篩這些", "這幾篇哪些值得讀"). Input items, mixed:
- **post URLs** (Threads/X) → fetched via `scrapling-fetcher`; if `ok:false`/明顯殘缺 → ask the user to paste that one's text (never score stub content).
- **pasted post texts**, separated by a `---` delimiter line.

## 3. Pipeline (two tiers)

1. **Collect list** (user-supplied).
2. **Fetch** each item: URL → scrapling-fetcher (`post_text`+`text_excerpt`); pasted text → use directly; stub → request paste.
3. **Tier 1 — light triage** (one sub-agent per post, `model: sonnet`, parallel in batches, **returns one line**):
   - Score dims **A/C/E/F/G** (sensational framing / numbers-without-premise / emotional hooks / fake authority / source present-or-not) from the text.
   - Extract cited references + quantitative claims.
   - **B/D depend on verification → left as "未深查 (pending)"**; the Tier-1 score is a conservative **初篩 (prelim)** that does NOT push to 🔴 on rhetoric alone.
   - Return: `分數/100 燈號(初篩) | 觸發 | 來源:有/無 | 一句話`.
4. **Aggregate**: rank by score desc; light light-distribution (how many 🟢🟡🟠🔴).
5. **Tier 2 — upgrade** the 🟠/🔴 (or user-named) posts → run the **full single-post Mode B** (deep-verify cited papers via paper-verify/pdf-extract → fills B/D, the claim-vs-paper gap) → template-E verdict; the post's score is re-labelled **深查 (verified)** and may change.
6. **Output**: `hype_check/批量貼文掃描_<label>.md` — ranked table + distribution + upgraded verdicts + method-limits note.

## 4. Scoring

Reuses the Mode B 7-dimension rubric (A–G).
- **Tier 1**: A/C/E/F/G scored from text; **B (claim-vs-paper gap) and D (hidden limitations) marked "待深查"** and the total is flagged 初篩/conservative. Rhetoric-only must not yield 🔴 — at most 🟠 with an "upgrade" recommendation, to honour 熱情≠營銷號.
- **Tier 2**: deep verification fills B/D; final score labelled 深查.
- Bands unchanged: 0–25 🟢 / 26–50 🟡 / 51–75 🟠 / 76–100 🔴.

## 5. Scale / cost

- N posts = N Tier-1 sub-agents (light, no source-opening) → default one round **N ≤ 15**; more → split into rounds and **tell the user first**.
- Parallel in batches (~5 concurrent). Tier-2 cost paid only for flagged posts.
- **No silent truncation**: always report how many scanned / of how many supplied.

## 6. Discipline (Mode B + batch)

- Stub/incomplete fetch → ask the user to paste; never score stub content.
- **熱情 ≠ 營銷號**: with B/D un-verified in Tier 1, do not call a post 🔴 on rhetoric alone — flag 🟡/🟠 and recommend upgrade.
- Score is heuristic, not a verdict; reproducible per the fixed rubric.
- **Batch results must not be used for public call-outs** — media-literacy / self-defense only (the ethics gate still applies; refuse "help me write takedowns of these accounts").

## 7. Components / files

- **Modify:** `skill/SKILL.md` (Mode B: add a 批量子流程 section), `skill/references/templates.md` (add **Template I** — Tier-1 one-line prompt + batch summary format).
- **Reuse (no new tool):** `scrapling-fetcher` (fetch), existing single-post Mode B (Tier-2 upgrade), `paper-verify`/`pdf-extract` (deep verification on upgrade).

## 8. Testing (RED→GREEN, sub-agent behavioral)

Feed a mixed batch and assert triage behavior:

| Post | Expected Tier-1 |
|---|---|
| Obvious hype (GraphCast 營銷號版: 末日/失業/無連結) | high score 🟠/🔴, flagged |
| Honest share (GraphCast 誠實版: 連結+限制+平實) | low 🟢, not false-flagged |
| "Real numbers, premise stripped" (Perplexity SaC thread) | 🟡 + **recommended for upgrade** (B/D pending) |
| Plain researcher share (DroPE) | low 🟢 |

GREEN: ranking is sensible, 🟢 not false-flagged, the premise-stripped one is routed to upgrade; after upgrade the deep verify produces the right gap verdict (template E). Reuse the project's existing example posts as the test set.

## 9. Roadmap linkage

Completes 1→2→4. Tier-2 upgrades automatically benefit from #1 (paper-verify facts) + #2 (pdf-extract full text + refs). Mirrors the existing Mode C batch sub-flow (list → one-agent-per-item one-liner → ranked table → upgrade suspicious to full report), keeping the two batch modes consistent.
