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
Mode C 取文/拆解 calls it once; C1/C4/C5 直接採用其結果(`retracted`/`not_in_doaj_journal`/`author_identity_weak`/引用統計)。Scoring stays in the Mode C rubric (e.g. `retracted` → 🔴 anchor).

## Honesty / limits (v1)
- **`work_not_found` ≠ fraud.** New arXiv papers (days old) are often not yet indexed → `resolved:false`; the skill **falls back to WebFetch checks**.
- **No ORCID ≠ fake author.** Only aggregated (`author_weak_ratio`) is a weak signal; never a verdict on an individual.
- Not covered v1: C2/C3 (need full text, roadmap #2), deep hallucinated-ref check (needs `--refs` from #2), PubPeer/predatory lists.
- Politeness: OpenAlex polite pool via `mailto`; modest ORCID calls.
