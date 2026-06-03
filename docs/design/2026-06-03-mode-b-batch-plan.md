# Mode B Batch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "批量子流程" to Mode B: a user-supplied list of posts → light Tier-1 triage (one line each) ranked → upgrade suspicious ones to full single-post Mode B.

**Architecture:** Documentation/skill change (markdown), no new code. Reuses scrapling-fetcher (fetch), existing single-post Mode B (Tier-2 upgrade), paper-verify/pdf-extract (deep verify on upgrade). Tested per writing-skills: subagent behavioral RED→GREEN on a mixed post batch (no pytest).

**Tech Stack:** Markdown skill files; Claude Code Agent/Skill/WebFetch; sub-agent behavioral tests.

**Spec:** `docs/design/2026-06-03-mode-b-batch-design.md`

**Testing model:** RED = a sub-agent WITHOUT the batch sub-flow on a mixed batch (observe over/under-flagging, no upgrade routing). GREEN = sub-agents following the written Tier-1 (one-liner per post) → sensible ranking, 🟢 not false-flagged, premise-stripped post routed to upgrade; then upgrade one → deep verify catches the gap. Same method as Mode C batch.

**Where:** edit `repo/skill/SKILL.md` + `repo/skill/references/templates.md`; Task 5 syncs to live `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\`. Commits local (no push).

---

## File Structure
| File | Change |
|---|---|
| `repo/skill/references/templates.md` | add **Template I** (Tier-1 one-line prompt + batch summary format) |
| `repo/skill/SKILL.md` | Mode B: add "批量子流程" section; frontmatter description: add batch trigger |

---

## Task 1: Add Template I to templates.md

**Files:** Modify `repo/skill/references/templates.md` (append at end)

- [ ] **Step 1: Append Template I**

Append to the end of the file:

```markdown
## I. Mode B 批量模式模板（使用者供清單;第一層一行 + 總表）

**清單**:使用者供——多個貼文 URL 與/或多則貼上內文(`---` 分隔)。URL → `scrapling-fetcher` 取文;殘缺/`ok:false` → 請補貼該則,不硬評。

**第一層 輕量篩 子代理**(每篇一個,`model:sonnet`,並行分批,只回一行):
\```
你在做「營銷號批量初篩」(讀者自保)。只看貼文文字做快速判讀,**不開來源深查**。評 5 維:A 標題/開場聳動、C 數字無前提/比較錯位、E 情緒操弄(失業/健康/FOMO/收藏轉發 CTA)、F 假權威/匿名背書、G 有無附可查證來源(arXiv/DOI/GitHub 連結)。**B(宣稱vs原文落差)與 D(隱瞞限制)需查證 → 一律標「待深查」,不要只憑話術就定 🔴(熱情≠營銷號)**。抽出貼文引用的論文/repo 與量化宣稱。
貼文:{POST}
**只回這一行**:`{標籤} | 初篩 分數/100 燈號 | 觸發:<維度或"無"> | 來源:有/無(<引用>) | B/D:待深查 | 一句話`
燈號 0–25🟢 / 26–50🟡 / 51–75🟠 / 76–100🔴;**話術濃但未查證 → 最多 🟠 並建議升級**。
\```

**第二層 升級**:🟠/🔴 或使用者指定 → 跑完整單篇 Mode B(模板 D 查證所引論文 + 模板 E 判決),補 B/D,分數改標「深查」。

**總表**(主代理彙整,存 `hype_check/批量貼文掃描_<標籤>.md`):免責標頭 + 燈號分布 + 表(#/標籤/分數(初篩|深查)/燈/來源/觸發/一句話)+ 升級判決區 + 方法限制(初篩未深查 B/D;掃 N/共 M)。
```
(Note: the `\``` are shown escaped here so this plan renders; when writing templates.md, use real triple-backticks for the inner prompt block.)

- [ ] **Step 2: Verify** — `grep -n "## I\." repo/skill/references/templates.md` shows the heading; confirm Template H (batch arXiv) still present above it.

- [ ] **Step 3: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add skill/references/templates.md
git commit -m "feat(mode-b): add Template I (batch triage + summary)"
```

---

## Task 2: Add the 批量子流程 section + trigger to SKILL.md

**Files:** Modify `repo/skill/SKILL.md`

- [ ] **Step 1: Append the 批量子流程 section after the "Mode B 紀律" block**

Find this exact line (last bullet of Mode B 紀律):
`- **取文殘缺就停**:寧可請使用者重貼,不要對殘缺內容硬打分。`
Append immediately after it:

```markdown

## Mode B 批量子流程（一次篩一批貼文）
使用者給**一批貼文**(多 URL 與/或多則內文,`---` 分隔)問「幫我一次篩 / 哪幾篇值得讀」。**使用者供清單,不自動爬時間軸。**
1. **取文**:URL → `scrapling-fetcher`;內文直接用;殘缺 → 請補貼該則,不硬評。
2. **第一層 輕量篩**:每篇一子代理(`model:sonnet`,並行分批,模板 I,只回一行)——評 A/C/E/F/G + 抽引用/宣稱;**B/D 標「待深查」**,話術濃但未查證最多 🟠(熱情≠營銷號,不憑話術定 🔴)。
3. **彙整**:依分數排序 + 燈號分布。
4. **第二層 升級**:🟠/🔴(或使用者指定)→ 跑完整單篇 Mode B(深查所引論文 vs 宣稱落差 → 補 B/D)→ 模板 E 判決,分數改標「深查」。
5. **輸出**:`hype_check/批量貼文掃描_<標籤>.md`(總表 + 分布 + 升級判決 + 方法限制)。

**批量紀律**:一輪預設 **N≤15**、更多分輪先告知;並行分批 ~5;取文殘缺→請補貼;**不靜默截斷**(掃 N/共 M);分數啟發式非定論;**批量結果不可拿去公開點名**(識讀/自保用途)。
```

- [ ] **Step 2: Add a batch trigger to the frontmatter description**
Find: `"營銷號分數", "hype score",`
Replace with: `"營銷號分數", "hype score", "一次篩這些貼文/批量篩貼文",`

- [ ] **Step 3: Verify** — `grep -n "批量子流程\|一次篩這些貼文" repo/skill/SKILL.md` shows both.

- [ ] **Step 4: Commit**
```bash
git add skill/SKILL.md
git commit -m "feat(mode-b): add batch sub-flow section + trigger"
```

---

## Task 3: RED baseline (document the gap)

**Files:** none (behavioral)

- [ ] **Step 1: Dispatch a baseline sub-agent (NO batch instructions)** with this mixed batch and prompt "幫我判斷這幾篇貼文哪些是營銷號、哪些值得讀,排個序":
  - **P1 (hype):** GraphCast 營銷號版 (「全人類的老天爺要被 AI 掌控了!…氣象局飯碗不保…末日來臨前搶先佈局…趕快收藏」, no link)
  - **P2 (honest):** GraphCast 誠實版 (「剛讀完 GraphCast (arXiv:2212.12794)…一分鐘出全球10天預報…要注意它從歷史統計外插、對極端事件較弱…」)
  - **P3 (premise-stripped):** Perplexity SaC thread (真數字 100%/−85.1%/2.5×, but WANDR 是自家未公開基準)
  - **P4 (plain):** DroPE share (「Sakana AI introduces DroPE… Paper: arxiv.org/abs/2512.12167」)

- [ ] **Step 2: Record baseline behavior** — note whether it scores from memory, over-flags the honest P2, fails to separate "needs verification" (P3) from obvious hype (P1), and produces no upgrade routing / no reproducible per-post score. This is the gap the batch sub-flow fills. Commit the observation:
```bash
git commit --allow-empty -m "test(mode-b-batch): RED baseline — ad-hoc ranking, no tiers/upgrade routing"
```

---

## Task 4: GREEN — Tier-1 triage + one upgrade

**Files:** none (behavioral, following the written Template I / sub-flow)

- [ ] **Step 1: Tier-1 — dispatch one sub-agent per post** (parallel), each given the Template I Tier-1 prompt + that post; each returns one line. Use P1–P4 above.
Expected:
  - P1 (hype) → 🟠/🔴, 觸發 A/E/G(no link), B/D 待深查
  - P2 (honest) → 🟢, **not false-flagged**, 來源:有, 觸發 無/輕
  - P3 (premise-stripped) → 🟡/🟠, 來源:有, **B/D 待深查 → recommended upgrade**
  - P4 (plain) → 🟢, 來源:有

- [ ] **Step 2: Aggregate** — rank by score; confirm ordering roughly P1 ≥ P3 > P2 ≈ P4, and that P3 is flagged for upgrade (the key "real numbers, premise stripped" case Tier-1 must route, not dismiss).

- [ ] **Step 3: Tier-2 upgrade P3** — dispatch a full single-post Mode B sub-agent on the Perplexity SaC post (deep-verify via WebFetch/paper-verify). Expect it to reproduce the ~27 🟡 verdict with the WANDR self-benchmark gap (B/D filled). Confirms upgrade path works.

- [ ] **Step 4: Record results** — commit the observation:
```bash
git commit --allow-empty -m "test(mode-b-batch): GREEN — tiers rank sensibly, honest not flagged, premise-stripped upgraded"
```

---

## Task 5: Sync to live + final commit

**Files:** copy the 2 markdown edits to live

- [ ] **Step 1: Apply the same 2 edits to the LIVE skill** (`C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\references\templates.md` Template I append; `...\SKILL.md` 批量子流程 section + description trigger), using the same exact anchor strings from Tasks 1–2. Read each live file first; do NOT whole-file copy (preserve live's Mode B absolute paths).

- [ ] **Step 2: Verify live** — `grep -rn "批量子流程\|## I\." "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/SKILL.md" "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/references/templates.md"` shows the additions.

- [ ] **Step 3: Final repo commit (local, NO push)**
```bash
cd /d/paper/hype_experiment_3/repo
git add -A
git commit -m "chore(mode-b-batch): sync batch sub-flow + Template I to live" --allow-empty
git log --oneline -1 ; git status -sb | head -1
```

---

## Self-Review
- **Spec coverage:** §2 input (user-supplied URLs/pasted, `---`)→T1/T2; §3 two-tier pipeline→T2 section + T1 Template I; §4 scoring (A/C/E/F/G; B/D pending; rhetoric≤🟠)→T1 prompt + T2; §5 scale (N≤15, batches, no silent truncation)→T2 紀律; §6 discipline (熱情≠營銷號, no public call-out)→T2 紀律; §7 components (no new tool, reuse)→all; §8 testing→T3 RED + T4 GREEN with the exact mixed batch.
- **Placeholder scan:** none — Template I and the SKILL.md section are given verbatim; test posts are concrete (P1–P4 from the project's own examples). The escaped-backtick note in Task 1 is an instruction to use real backticks, not a placeholder.
- **Consistency:** "批量子流程" section, "Template I", "初篩/深查" labels, bands (🟢🟡🟠🔴), and the upgrade trigger (🟠/🔴 or user-named) are used identically across T1, T2, T4. Tier-1 dims A/C/E/F/G + B/D-pending consistent between Template I (T1) and the SKILL section (T2).
