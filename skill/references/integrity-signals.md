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
