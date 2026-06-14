<p align="center">
  <img src="./cover.png" alt="Dissecting Paper Hype — see what the paper says, see what the internet claims" width="760">
</p>

# Dissecting Paper Hype

*A [Claude Code](https://claude.com/claude-code) skill for media literacy on AI‑paper hype.*

繁體中文版 → [README.zh-TW.md](./README.zh-TW.md)

---

Social feeds (Threads, X, …) are flooded with posts that take a real research paper and inflate it into a "this changes everything / your job is doomed" clickbait. This skill helps you **see through that** — in two directions.

## Four modes

### Mode A — Study (paper → hype → dissection)
Give it a research domain (or your own notes). It dispatches sub‑agents to find **real** papers, then for each paper produces:
- an honest **plain‑language summary** (with the real limitations), and
- a deliberately exaggerated **hype rewrite** (sensational title + clickbait body),

then scores every piece on a 6‑dimension rubric and writes an analysis report of the recurring **tactics, high‑frequency phrases, and sentence templates**. The point is to learn the manipulation playbook by reconstructing it.

> ⚠️ Every generated hype piece carries a disclaimer header marking it as a **controlled media‑literacy demo, not a real evaluation**. This skill is **not** for producing publishable marketing copy — that use is refused by an ethics gate.

### Mode B — Quick‑check (post → 0–100 hype score)
Paste a single Threads/X post (URL or text) and ask *"is this hype?"*. The skill:
1. **Fetches** the post (Docker/Scrapling container, or you paste the text),
2. **Extracts** its claims, cited papers/repos, and rhetorical tells,
3. **Verifies** — dispatches sub‑agents that actually open each cited arXiv/GitHub link and compare *what the post claims* vs *what the paper really says*, and which limitations were omitted,
4. **Scores** it 0–100 on a 7‑dimension rubric and returns a verdict.

The verification step is the whole point: it catches the most common trick — **real numbers with the premises stripped out** — which a keyword scan (or a from‑memory guess) cannot.

#### Hype‑score rubric (0–100, higher = more suspicious)
| Dim | What it measures | Max |
|---|---|---|
| A | Sensational title / opening | 15 |
| B | Claim‑vs‑paper gap *(needs verification)* | 15 |
| C | Numbers stripped of premises / mismatched comparison | 15 |
| D | Hidden limitations *(needs verification)* | 15 |
| E | Emotional manipulation (job‑loss / health / FOMO / nationalism) | 15 |
| F | Fake authority / fake social proof | 15 |
| G | Unverifiable sources | 10 |

Bands: **0–25 🟢 worth reading · 26–50 🟡 verify before trusting · 51–75 🟠 highly suspect · 76–100 🔴 textbook hype, scroll past.**

> A real number you can verify is *not* a sin; a fabricated one, or a real one with its premise hidden, is. **Enthusiasm ≠ hype** — the gap and the omission are what the score punishes.

### Mode C — Paper integrity triage (reader self-defense)
Give it a paper link (arXiv/DOI/URL) and ask *"is this trustworthy / any fraud?"*. It verifies the paper's **own** integrity — checking for **nonexistent / hallucinated references, leftover AI-generation text, tortured phrases, retraction / PubPeer status, and predatory venues** — and returns a 0–100 **trust-risk** score with an evidence dossier. Scoped to *your own* decision (trust / cite / build on), **not** public accusation: every flag is a verifiable lead, "查不到 ≠ fraud", and a clean score ≠ "the paper is correct."

### Mode D — GitHub trending hype check (reader self-defense)
Ask it to scan **GitHub trending** (daily / weekly / monthly) for over‑hyped or "star‑inflated" repos. It fetches the board, triages suspects (extraordinary headlines like `every` / `#1` / `super intelligence`, hot‑keyword markdown packs, checkable quantitative claims), then — for each suspect — **opens the actual body** (the repo page *and* the raw `SKILL.md` / `README` / source) and scores the **headline‑vs‑body gap** 0–100 on a 6‑dimension rubric.

#### Hype‑score rubric (0–100, higher = more suspicious)
| Dim | What it measures | Max |
|---|---|---|
| D1 | Headline‑vs‑body gap *(needs reading the body)* | 25 |
| D2 | Hidden limitations (no Limitations section / absolute words contradicted by its own table) | 20 |
| D3 | Use‑case mismatch (reproducible benchmark ≠ useful for *your* task) | 15 |
| D4 | Absolute / self‑anointing claims (`every` / `#1` / `super intelligence`) | 15 |
| D5 | Rule or code density (markdown pack: concrete & verifiable vs platitudes) | 15 |
| D6 | Author / commercial signals (throwaway account, "free" but hosted‑backend by default) | 10 |

Bands: **0–25 🟢 solid · 26–50 🟡 verify + check fit · 51–75 🟠 headline badly inflated, treat as prototype · 76–100 🔴 hollow or deceptive.**

> The soul of Mode D is **actually opening the body**: "all markdown" ≠ empty (the substance is rule density, not whether there's code), a pretty benchmark ≠ useful for your use‑case, and viral ≠ bot‑inflated. You can't confirm star bots from outside — only the claim‑vs‑body gap. Reader self‑defense, **not** public accusation.

## Mode B in action
Asked *"is this hype?"* on a real X thread about Perplexity's "Search as Code" architecture, Mode B fetched the post, opened Perplexity's actual research article, and returned this verdict:

> ### 🟡 Hype score: 27 / 100 — *verify before trusting*
> **Verdict:** An honest, careful technical summary — every quoted number matches the source, tone is measured, sources check out. Its one real flaw: it relays a **vendor's first‑party benchmark (WANDR wasn't public yet) as if it were independent**. Read it, but know whose scoreboard you're looking at.
>
> | Dim | Score | Why |
> |---|---|---|
> | A · sensational title | 4/15 | "next paradigm shift" is mild; no shock words |
> | B · claim‑vs‑paper gap | 4/15 | every quoted number matches the article |
> | C · numbers w/o premise | 7/15 | "competitors <25%", "2.5×" are vendor‑run comparisons |
> | D · hidden limitations | 8/15 | omits: self‑designed benchmark, no third‑party check |
> | E · emotional manipulation | 1/15 | no FOMO / job‑loss / call‑to‑action |
> | F · fake authority | 2/15 | cites the real source (which *is* the vendor) |
> | G · unverifiable sources | 1/10 | the article is fully verifiable |
>
> **Verification step:** opened `research.perplexity.ai/...` → `100% accuracy` ✓ · `−85.1% tokens` ✓ · `2.5× on WANDR` ✓ — every number real, but WANDR is Perplexity's own benchmark, unpublished at post time.

<!-- Prefer an actual screenshot? Drop a PNG at assets/mode-b-demo.png and replace the block above with: ![Mode B demo](./assets/mode-b-demo.png) -->

## Limitations — read before trusting a score

The scores are **triage to guide a human, not ground truth.** Empirically measured limits (numbers from [calibration](./docs/calibration-2026-06.md) and the [20-paper Mode C test](./docs/mode-c-test-2026-06.md)):

- **"Not found" is not a verdict.** Very recent papers aren't yet in OpenAlex, so the verifier returns `resolved:false` and falls back to manual checks. A brand-new paper is **not** a red flag. (2 of 20 test papers hit this.)
- **`refs_unresolved` is advisory, never decisive.** Live C1 ran **12–55% of references "unresolved" on legitimate papers** — all false positives, driven by messy reference extraction, not fraud. A high unresolved count means "go check manually," not "fake citations." Running a **GROBID** service (see `skill/pdf-extract/`) gives cleaner references and a more reliable C1.
- **The venue/DOAJ flag can't identify predatory journals.** It fires identically on a Beall's-List journal (e.g. IJISRT) and on reputable subscription journals (BMJ, Review of Economic Studies), because DOAJ only indexes open-access titles. The predatory call needs the **qualitative C5 check** (Beall's list / hijacking / fake impact factor), not the flag alone.
- **C2/C3 (AI-text traces, tortured phrases) need full text.** Image-only / scanned PDFs yield `coverage:none`; those checks are reported as limited, not "passed."
- **Mode B depends on a live fetch.** Login walls, anti-bot, or deleted posts can block fetching; the skill says so rather than guessing.
- **Mode C is reader self-defense, not accusation.** "查不到 ≠ fraud", and a clean score ≠ "the paper is correct." Calibration sets are small (stated N); treat the numbers as indicative.

## Requirements
- **Claude Code** (this is a skill — it uses the `Skill` tool, sub‑agents, and web access).
- For Mode B's deep verification: web access (`WebFetch`/`WebSearch`).
- For fetching JS‑heavy social posts: **Docker** (optional — you can always just paste the post text).

## Install

### Option A — let your AI agent install it (recommended)
Paste this prompt to Claude Code (or any coding agent with shell access) and it will install the skill itself:

```text
Install the "dissecting-paper-hype" Claude Code skill from https://github.com/GMfatcat/Paper-Hype

1. Clone (or download) the repo to a temp location.
2. Copy its `skill/` directory into my personal skills directory so the result is
   ~/.claude/skills/dissecting-paper-hype/  containing SKILL.md, references/ and scrapling-fetcher/.
   (Windows: %USERPROFILE%\.claude\skills\dissecting-paper-hype\)
3. Optional — build the post fetcher: in skill/scrapling-fetcher run  `docker build -t hype-fetcher .`
4. Verify SKILL.md exists at the target path, then read it and summarize the four modes back to me.
```

### Option B — manual
```bash
# macOS / Linux
git clone https://github.com/GMfatcat/Paper-Hype
cp -r Paper-Hype/skill ~/.claude/skills/dissecting-paper-hype

# Windows (PowerShell)
git clone https://github.com/GMfatcat/Paper-Hype
Copy-Item -Recurse Paper-Hype\skill "$env:USERPROFILE\.claude\skills\dissecting-paper-hype"
```

Then in Claude Code just ask naturally — the skill triggers on phrases like *"做營銷號實驗"*, *"把論文寫成吹捧版"* (Mode A), *"這篇貼文是營銷號嗎 / is this post hype? <URL>"* (Mode B), *"這篇論文可信嗎 / is this paper legit? <link>"* (Mode C), or *"掃 github trending / which trending repos are over‑hyped?"* (Mode D).

## Docker fetcher (Mode B 取文)
Packages [Scrapling](https://github.com/D4Vinci/Scrapling) so you don't install Python/Playwright on the host.
```bash
cd skill/scrapling-fetcher
docker build -t hype-fetcher .
docker run --rm hype-fetcher "https://www.threads.com/@user/post/XXXX"
```
Outputs one JSON object; use `post_text` + `text_excerpt` as the post body. **Tested (2026‑06):** the stealth fetcher (camoufox, runs JS) successfully retrieved a full **public Threads** post and arXiv pages; **X (Twitter) login‑walls** often leave only a stub → fall back to pasting. See [skill/scrapling-fetcher/README.md](./skill/scrapling-fetcher/README.md).

## Repo layout
```
skill/                     the installable Claude Code skill
  SKILL.md                 modes, pipelines, rubrics, hard rules
  references/templates.md  sub‑agent prompts + report formats
  scrapling-fetcher/       Dockerized post fetcher (Dockerfile + fetch.py)
examples/                  experiment data — 25 domains, 75 hype pieces
  batch1-niche-ai/         10 niche domains (KAN, SNN, Liquid NN, …)
  batch2-mainstream/       5 mainstream domains (Agents, RAG, Diffusion, …)
  batch3-hot/              10 hot domains (Quantization, MoE, Alignment, AI4Science, …)
  cross-batch-playbook.md  the consolidated anti‑hype field guide
```

## Ethics & disclaimer
`examples/` contains **deliberately fabricated** clickbait rewrites of real papers, produced as teaching material. Every file is headed with a disclaimer in Chinese marking it as a controlled demo. **Do not extract and publish any "營銷號版 (hype version)" as a real take on a paper.** The skill exists to *detect and dissect* hype, never to manufacture it.

## Calibration

**Calibration (indicative, small self-built sets — see [docs/calibration-2026-06.md](./docs/calibration-2026-06.md)):** C1 hallucinated-fake recall ≈ 82% on fully fabricated fakes (n=200 hard set); the earlier 26% was a dataset artifact — perturbed fakes retained real title tokens so Crossref resolved them as real papers. C1 reference-resolution false-positive ≈ 21–23% (fuzzy-match floor on DOI-less refs; DOI-direct addition is principled but did not reduce FP on this DOI-sparse dataset) — which is why `refs_unresolved` is an *advisory*, non-decisive signal. `author_identity_weak` false-positive 0% on legit large-team papers (n=5); C4 retraction detection 3/3 on known cases (OpenAlex coverage, n=7). Numbers are honest point estimates with stated N, including the unflattering ones.

**End-to-end Mode C run on 20 fresh, previously-untested papers** (see [docs/mode-c-test-2026-06.md](./docs/mode-c-test-2026-06.md)): C4 retraction anchored both seeded retracted papers to 🔴; brand-new papers not yet indexed fell back to manual (⚪) rather than being penalised; no real author team tripped `author_identity_weak`. Two honest limits surfaced and documented: the DOAJ flag cannot distinguish a Beall's-List journal (IJISRT) from reputable subscription journals (BMJ, Rev. Econ. Studies) — predatory calls need the qualitative C5 check; and live C1 reference resolution ran 12–55% unresolved on legitimate papers (all false positives, driven by messy arXiv-HTML reference extraction), re-confirming that `refs_unresolved` is advisory and that GROBID-quality references are the real C1 lever.

## Acknowledgements
Mode B's post fetcher is built on [**Scrapling**](https://github.com/D4Vinci/Scrapling) by Karim Shoair ([@D4Vinci](https://github.com/D4Vinci)) — an adaptive web‑scraping framework that handles JS rendering and anti‑bot, which is what makes fetching live Threads/X posts possible. This project only **invokes** Scrapling inside a Docker container (see `skill/scrapling-fetcher/`); it does not vendor or modify Scrapling's source.

## License
This project is licensed under the [MIT License](./LICENSE) © 2026 GMfatcat.

**Third‑party licenses:**
- [Scrapling](https://github.com/D4Vinci/Scrapling) — **BSD‑3‑Clause** © Karim Shoair.
- The Docker image additionally installs Python, Playwright / camoufox and their dependencies, each under its own license.
