# Mode C — Paper Integrity Triage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third mode ("Mode C") to the `dissecting-paper-hype` skill that takes a paper link and returns a private *trust-risk* score (0–100) + an evidence dossier, for reader self-defense.

**Architecture:** Mode C reuses the skill's existing machinery — mode router, the "verify via sub-agent, never from memory" discipline, and the report-template style. Fetching uses **WebFetch** for arXiv/DOI/open-access full text + reference list (the same way Mode B already opens cited papers); the `scrapling-fetcher` container is only an optional fallback for JS-heavy publisher pages. Five high-signal, fully-automatable checks run as parallel sub-agents, then aggregate to a score.

**Tech Stack:** Markdown skill files (`SKILL.md`, `references/*.md`); Claude Code `Skill`/`Agent`/`WebFetch`/`WebSearch` tools; sub-agent behavioral tests (no pytest — this is a skill, tested per writing-skills).

**Important — testing model:** This builds documentation that steers an agent, so "RED→GREEN" means:
- **RED** = dispatch a sub-agent WITHOUT the new Mode C instructions on a test paper; observe it score from memory / skip lookups.
- **GREEN** = dispatch a fresh sub-agent following the written Mode C pipeline; confirm it performs real lookups and produces the right verdict.
Same method we used for Mode B earlier in this project.

**Spec:** `docs/design/2026-06-02-mode-c-paper-integrity.md`

**Scope guard:** Self-defense triage only. No public-accusation / report-filing output. Image forensics and large-corpus plagiarism are explicitly out of v1.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `references/integrity-signals.md` | **Create** | Data the checks need: AI-generation trace strings, tortured-phrase examples + source, and the lookup endpoints (Crossref / arXiv / Retraction Watch / PubPeer / DOAJ). |
| `references/templates.md` | **Modify** | Add **Template F** (per-check integrity sub-agent prompts) and **Template G** (Mode C verdict report). |
| `SKILL.md` | **Modify** | (a) frontmatter `description` → add Mode C triggers; (b) mode router 兩種→三種; (c) new "MODE C" section (ethics gate, fetch, pipeline, 5 checks, scoring, honesty rules). |

All paths are relative to the skill root `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\`.
The skill is also mirrored in the repo at `repo/skill/` — after the skill is validated, copy the changed files there (Task 8) so the open-source repo stays in sync.

---

## Task 1: Create the integrity-signals reference data file

**Files:**
- Create: `references/integrity-signals.md`

- [ ] **Step 1: Write the data file**

Write this exact content to `references/integrity-signals.md`:

```markdown
# Integrity signals — data for Mode C checks

## C2 · AI-generation trace strings (literal text that should never appear in a real paper)
Case-insensitive substring search over the full text. Any hit is a strong flag.
- "as an AI language model"
- "as a large language model"
- "I cannot provide" / "I cannot fulfill"
- "Certainly, here is" / "Sure, here is a possible"
- "Regenerate response"
- "as of my last knowledge update" / "my last training update"
- "I'm sorry, but I cannot"
- "this is a possible introduction for your topic"
- "I hope this helps" (only flag in body/methods, not in acknowledgements)
- "[insert citation]" / "[insert reference]" / "as an AI"

## C3 · Tortured-phrase fingerprints (paraphrase-mill tells)
Source of truth & live list: Problematic Paper Screener — https://www.irit.fr/~Guillaume.Cabanac/problematic-paper-screener
Well-known examples (match these + anything structurally similar):
| Tortured | Should be |
|---|---|
| colossal information / big information | big data |
| counterfeit consciousness / counterfeit neural | artificial intelligence / neural network |
| irregular esteem | random value |
| mean square mistake | mean square error |
| bosom peril | breast cancer |
| profound learning | deep learning |
| haze figuring | cloud computing |
| underpins vector machine | support vector machine |

## Lookup endpoints (use via WebFetch/WebSearch; never assert from memory)
- Reference existence / metadata: Crossref `https://api.crossref.org/works?query.bibliographic=<citation>` ; DOI resolve `https://doi.org/<doi>` ; arXiv `https://arxiv.org/abs/<id>`
- Retraction status: Retraction Watch database (search the title/DOI/author) ; the paper's publisher page (look for "Retracted"/"Expression of Concern")
- Post-publication review: PubPeer `https://pubpeer.com/search?q=<doi-or-title>`
- Venue legitimacy: DOAJ `https://doaj.org/search/journals?source=...` ; check if the journal is indexed; watch for hijacked-journal / fake-impact-factor signals
```

- [ ] **Step 2: Verify the file exists and is well-formed**

Run: `wc -l references/integrity-signals.md`
Expected: ~30+ lines, no error.

- [ ] **Step 3: Commit**

```bash
git add references/integrity-signals.md
git commit -m "feat(mode-c): add integrity-signals data (AI traces, tortured phrases, lookup endpoints)"
```

---

## Task 2: Add Template F and Template G to templates.md

**Files:**
- Modify: `references/templates.md` (append two new sections after the existing Template E / Mode B section)

- [ ] **Step 1: Append Template F (per-check integrity sub-agent prompts)**

Append to `references/templates.md`:

```markdown
## F. Mode C 查證 subagent 模板（每項檢查一個,model: sonnet,並行派）

共同前綴(每個都加):
「這是一個論文採信風險查證任務(讀者自保用,非指控)。請用繁體中文,**務必實際用 WebFetch/WebSearch 查證,不可憑記憶斷言**。查不到就回報『不可查證』,不要當成造假也不要當成真實。」

- **C1 幻覺/不存在引用**：給定參考文獻清單 `{refs}`(過多時取樣 N 筆並回報「已查 N / 共 M」)。對每筆用 Crossref/DOI/arXiv 核對是否存在、標題-作者-年份是否吻合。回傳:`已查/總數`、`確認不存在` 筆數與清單、`無法確認` 筆數、一句總評。
- **C2 AI 生成痕跡**：給定全文 `{fulltext}` 與 `integrity-signals.md` 的 AI 字串清單。回傳:命中字串 + 出現位置原句(照抄)、或「無命中」。
- **C3 tortured phrases**：給定全文與 tortured 清單(+ Problematic Paper Screener)。回傳:命中片語 + 原句、或「無命中」。
- **C4 撤稿/PubPeer**：給定 標題/DOI/作者。查 Retraction Watch、publisher 頁、PubPeer。回傳:`已撤稿/關注聲明/PubPeer 有討論/查無`,附連結。
- **C5 掠奪性/可疑出版**：給定 venue 名稱/DOI。查 DOAJ 是否收錄、掠奪/劫持期刊跡象、假影響因子。回傳:`正規/可疑/掠奪/查無`,附依據連結。

每個 subagent **只回傳該項結構化結果**(精簡),不要長篇。

## G. Mode C 判決報告格式（主代理輸出;存檔走 `hype_check/論文判決_<標籤>.md`）

```
# 論文採信風險快篩：<論文標題>
> ⚠️ 自動化啟發式參考,讀者自保用,非造假定論。乾淨分數 ≠ 論文正確,只代表未掃到自動化紅旗。
> 取文涵蓋度:<全文取得 / 僅摘要+引用(檢查受限)>。已查引用 <N>/<總數>。

## 採信風險:NN / 100　→　🔴/🟠/🟡/🟢 <燈號文字>
一句話結論:<可信 / 自己再查 / 存疑 + 最大旗標>

## 檢查結果
| 檢查 | 結果 | 證據(照抄/連結) | 信心 | 你該自己再查什麼 |
|---|---|---|---|---|
| C1 幻覺引用 | … | … | … | … |
| C2 AI 痕跡 | … | … | … | … |
| C3 tortured phrases | … | … | … | … |
| C4 撤稿/PubPeer | … | … | … | … |
| C5 掠奪性出版 | … | … | … | … |

## 給讀者的一句話
<要不要採信/引用、若要該先自己確認什麼>
```
```

- [ ] **Step 2: Verify the append**

Run: `grep -n "## F\.\|## G\." references/templates.md`
Expected: both `## F.` and `## G.` headings found.

- [ ] **Step 3: Commit**

```bash
git add references/templates.md
git commit -m "feat(mode-c): add Template F (integrity checks) and Template G (verdict report)"
```

---

## Task 3: Update SKILL.md — description + mode router

**Files:**
- Modify: `SKILL.md` (frontmatter `description`; the "兩種模式" router section)

- [ ] **Step 1: Extend the frontmatter description**

Replace the `description:` value's tail so it adds Mode C. Append this sentence inside the description (before the final list of triggers):
`MODE C (paper integrity): given a paper link (arXiv/DOI/URL) asking "is this paper trustworthy / any fraud", verify its references/venue/retraction status and return a 0–100 trust-risk score (reader self-defense, not accusation).`
And add triggers: `"這篇論文可信嗎", "有沒有造假", "該不該引用這篇", "is this paper legit"`.

- [ ] **Step 2: Convert the router from two modes to three**

Find the `## 兩種模式（先判斷走哪條）` section. Rename heading to `## 三種模式（先判斷走哪條）` and add this bullet after the Mode B bullet:

```markdown
- **MODE C 快篩模式·論文版**(論文連結 → 0–100 採信風險分數):使用者**給一篇論文(arXiv/DOI/URL)問「這篇可信嗎 / 有沒有造假 / 該不該引用」**。跳到〈MODE C:論文採信風險快篩〉。
```

And extend the ethics line to:
```markdown
- 倫理硬關卡三模式都適用:都不產出可發布行銷文;Mode B 只判讀貼文;**Mode C 只做讀者自保判讀,不產出公開點名/檢舉內容**。
```

- [ ] **Step 3: Verify**

Run: `grep -n "三種模式\|MODE C" SKILL.md`
Expected: heading renamed + Mode C router bullet present.

- [ ] **Step 4: Commit**

```bash
git add SKILL.md
git commit -m "feat(mode-c): add Mode C to description and mode router"
```

---

## Task 4: Add the MODE C section body to SKILL.md

**Files:**
- Modify: `SKILL.md` (append a new top-level section after the Mode B block, before any trailing shared sections)

- [ ] **Step 1: Append the Mode C section**

Append this section to `SKILL.md`:

```markdown
---
# ═══════ MODE C:論文採信風險快篩（論文連結→0–100 採信風險） ═══════

## 何時走這條
使用者給一篇論文(arXiv/DOI/URL)問「這篇可信嗎 / 有沒有造假 / 該不該引用」。產出:**採信風險分數 0–100**(越高越該謹慎)+ 燈號 + 證據卷宗,**給讀者自己判斷用**。

## Confirm First（倫理關卡)
- 正常用途(我該不該信/引用這篇)→ 放行。
- 若使用者要「公開點名 / 寫檢舉文 / 產出指控某人的內容」→ **停止**,說明 Mode C 只做讀者自保判讀。
- 鐵則:**查不到 ≠ 造假**(標「不可查證」);**絕不憑記憶斷言**論文或引用的事實,一律 WebFetch/WebSearch 查;**乾淨分數 ≠ 論文正確**,只代表未掃到自動化紅旗。

## 取文
連結 → WebFetch 取 metadata + 摘要 + **全文**(arXiv HTML/PDF、開放取用)+ **參考文獻清單**。
- 只拿到摘要(付費牆)→ 標「全文不可得 → 檢查受限」,降信心續跑,**不可當成完整檢查**。
- 一般頁面用 WebFetch;JS 重的出版頁可退用 `scrapling-fetcher/` 容器。

## Pipeline
1. **取文**(上方)。
2. **拆解**:參考文獻清單、全文正文、venue/DOI、作者。
3. **平行查 5 項**(每項一個 subagent,`model: sonnet`,模板 F;資料見 `references/integrity-signals.md`):
   - **C1 幻覺/不存在引用**(逐筆核 Crossref/DOI/arXiv;過多取樣並揭露)← 最強
   - **C2 AI 生成痕跡**(全文掃 AI 殘留字串)
   - **C3 tortured phrases**(洗稿指紋)
   - **C4 撤稿/PubPeer 狀態**(Retraction Watch + PubPeer + publisher 頁)
   - **C5 掠奪性/可疑出版**(DOAJ / 劫持期刊 / 假影響因子)
4. **整合評分 + 卷宗**(下方 rubric),每條 finding 附證據+出處+信心+「你該自己再查什麼」。
5. **判決報告**(模板 G)。

## Mode C 評分 Rubric（採信風險 0–100,越高越該謹慎）
| 代號 | 檢查 | 上限 |
|---|---|---|
| C1 | 幻覺/不存在引用 | 30 |
| C2 | AI 生成痕跡 | 25 |
| C4 | 撤稿/PubPeer | 25 |
| C5 | 掠奪性/可疑出版 | 15 |
| C3 | tortured phrases | 15 |

計分:各項依命中嚴重度給該項 0~上限分,加總後**歸一化到 0–100**。
燈號:**0–20 🟢 無重大旗標 / 21–45 🟡 輕微-自己查 / 46–70 🟠 多項旗標-存疑 / 71–100 🔴 嚴重-未獨立查證勿採信**。
涵蓋度調整:全文不可得時,需全文的項目(C1 全清單、C2、C3)只能部分執行 → 報告**降涵蓋度/信心**,不可當「通過」。

## Mode C 紀律（務必遵守）
- 絕不憑記憶說某引用是假的 — 必須查;區分「無法確認存在」vs「確認不存在」。
- 某來源連不上 → 標該項「未執行」,非「通過」。
- 參考文獻過多 → 取樣並**揭露**(已查 N / 共 M),不靜默截斷。
- 全文殘缺 → 明說涵蓋受限、降信心,不硬給高信心分數。
```

- [ ] **Step 2: Verify the section landed and no stale text**

Run: `grep -n "MODE C:論文採信風險\|採信風險 Rubric\|C1 幻覺" SKILL.md`
Expected: section heading + rubric + C1 present.

- [ ] **Step 3: Commit**

```bash
git add SKILL.md
git commit -m "feat(mode-c): add full Mode C section (pipeline, 5 checks, scoring, discipline)"
```

---

## Task 5: RED baseline test (document the gap Mode C fills)

**Files:** none (behavioral test via sub-agent)

- [ ] **Step 1: Dispatch a baseline sub-agent (NO Mode C instructions)**

Use the Agent tool, `model: sonnet`, prompt:
```
我讀到一篇論文,arXiv:2212.12794。請判斷它可不可信、該不該引用,給 0–100 採信風險分數(越高越該謹慎),簡短說明理由。
```

- [ ] **Step 2: Record the baseline behavior**

Expected (the gap): the sub-agent answers largely from memory, with **few or zero tool calls** (`tool_uses` ~0), does **not** look up the reference list, retraction status, or PubPeer. Note this verbatim in the commit message / a scratch note. This is the "test fails" state that justifies Mode C.

- [ ] **Step 3: Commit the observation**

```bash
git commit --allow-empty -m "test(mode-c): RED baseline — agent scores paper from memory, no lookups"
```

---

## Task 6: GREEN tests on four paper types

**Files:** none (behavioral tests via sub-agents following the Mode C pipeline)

For each, dispatch a sub-agent (`model: sonnet`) given the Mode C pipeline + rubric + discipline (from SKILL.md) and the paper, then check the expected outcome.

- [ ] **Step 1: Clean reputable paper — must NOT be false-flagged**

Paper: `arXiv:2212.12794` (GraphCast — already verified solid in this project).
Expected: references resolve, no AI traces, not retracted, reputable venue → **🟢 (0–20)**. The critical anti-false-positive test. If it scores >20, the rubric/instructions over-penalize → fix in Task 7.

- [ ] **Step 2: Paper with AI-generation traces / tortured phrases**

Find one: WebSearch `"as an AI language model" site:sciencedirect.com` or pick a current entry from the Problematic Paper Screener (https://www.irit.fr/~Guillaume.Cabanac/problematic-paper-screener). Use its DOI/URL.
Expected: **C2 and/or C3 fire with the offending sentence quoted**; score lands 🟠/🔴.

- [ ] **Step 3: Retracted paper**

Find one: search the Retraction Watch database for a retracted paper with an accessible record (or use a well-documented retraction). Use its DOI/title.
Expected: **C4 fires**, cites the retraction notice/PubPeer link; score 🟠/🔴.

- [ ] **Step 4: Paywalled paper — graceful degradation**

Use any ScienceDirect/Springer DOI whose full text is paywalled.
Expected: report says **"full-text unavailable → limited check," reduced confidence**, still checks what's available (refs in the record, venue, retraction status); **no overclaim**.

- [ ] **Step 5: Commit the test results**

```bash
git commit --allow-empty -m "test(mode-c): GREEN — clean=green, AI/tortured fire, retracted fires, paywalled degrades"
```

---

## Task 7: REFACTOR — close gaps found in testing

**Files:** `SKILL.md` and/or `references/templates.md`, `references/integrity-signals.md` (as needed)

- [ ] **Step 1: Apply fixes**

If any GREEN test missed (e.g., clean paper over-penalized, a check didn't actually call tools, paywalled overclaimed), edit the relevant Mode C wording / template / rubric to close the specific loophole. Show the exact edit.

- [ ] **Step 2: Re-run the affected GREEN test**

Re-dispatch the sub-agent for the failing case; confirm the expected outcome now holds.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "fix(mode-c): close gaps from GREEN testing"
```

---

## Task 8: Sync the validated skill into the open-source repo

**Files:** copy from skill root → `repo/skill/`

- [ ] **Step 1: Copy changed files**

```bash
cp "<skill-root>/SKILL.md" repo/skill/SKILL.md
cp "<skill-root>/references/templates.md" repo/skill/references/templates.md
cp "<skill-root>/references/integrity-signals.md" repo/skill/references/integrity-signals.md
```
(Then re-apply the repo path sanitization if any absolute paths slipped in — grep for `GMfatcat`/`D:\\paper`.)

- [ ] **Step 2: Update repo README (both languages)**

Add a Mode C row to the two-mode description in `repo/README.md` and `repo/README.zh-TW.md` (a "Mode C — paper integrity triage" bullet + a one-line note that it's self-defense, not accusation).

- [ ] **Step 3: Commit (local; do NOT push — design/build phase stays local per user)**

```bash
cd repo
git add skill/ README.md README.zh-TW.md
git commit -m "feat: add Mode C (paper integrity triage) to skill + README"
```

---

## Self-Review (run after the plan is written)

- **Spec coverage:** §1 framing → Task 4 ethics gate; §4 fetch → Task 4 取文; §6 five checks → Tasks 1,2,4; §7 scoring → Task 4 rubric; §8 report → Task 2 Template G; §9 honesty → Task 4 discipline; §10 reuse/new → Tasks 1–4; §11 testing → Tasks 5–7. All covered.
- **Placeholders:** test papers for Task 6.2/6.3 are specified by method + anchor source (Problematic Paper Screener / Retraction Watch) rather than a hardcoded DOI, because retraction/AI-trace exemplars change over time — this is a deliberate, instruction-complete choice, not a TBD.
- **Naming consistency:** check IDs C1–C5 and the file names (`integrity-signals.md`, Template F/G) are used identically across Tasks 1, 2, 4.
