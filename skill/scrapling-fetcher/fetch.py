#!/usr/bin/env python3
"""Scrapling-based post fetcher — Mode B 取文 adapter for the dissecting-paper-hype skill.

Usage:  python fetch.py <URL>
Output: a single JSON object on stdout, e.g.
  {"ok": true, "url": "...", "fetcher": "StealthyFetcher", "status": 200,
   "og_title": "...", "og_description": "<貼文文字>", "jsonld_text": "...",
   "post_text": "<最佳猜測的貼文內文>", "text_excerpt": "<可見文字前 4000 字>", "note": ""}

設計目標:抓 Threads/X 等社群貼文內文。策略由穩到強:
  1. StealthyFetcher（camoufox/Firefox 反偵測，能跑 JS、繞反爬）
  2. 退回 Fetcher（httpx，不跑 JS，但 og:description 這類連結預覽 meta 常在初始 HTML 就有）
若 ok=false 或 post_text 為空 → skill 應改請使用者「直接貼上貼文內文」，不要硬評分。
診斷訊息一律走 stderr，stdout 只留乾淨 JSON。
"""
import sys
import json
import re


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _meta(html, prop, attr="property"):
    """抓 <meta {attr}="prop" content="...">（content 在前在後都吃）。"""
    pat1 = r'<meta[^>]+%s=["\']%s["\'][^>]*\bcontent=["\']([^"\']*)["\']' % (attr, re.escape(prop))
    m = re.search(pat1, html, re.I)
    if not m:
        pat2 = r'<meta[^>]+\bcontent=["\']([^"\']*)["\'][^>]*%s=["\']%s["\']' % (attr, re.escape(prop))
        m = re.search(pat2, html, re.I)
    return m.group(1).strip() if m else ""


def extract(html):
    out = {
        "og_title": _meta(html, "og:title"),
        "og_description": _meta(html, "og:description"),
        "meta_description": _meta(html, "description", "name"),
        "jsonld_text": "",
    }
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.I | re.S,
    ):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict):
                for k in ("articleBody", "text", "caption", "description"):
                    if it.get(k):
                        out["jsonld_text"] = str(it[k]).strip()
                        break
            if out["jsonld_text"]:
                break
        if out["jsonld_text"]:
            break
    return out


def _safe_text(page):
    for attempt in (
        lambda: page.get_all_text(ignore_tags=("script", "style")),
        lambda: page.get_all_text(),
        lambda: getattr(page, "text", ""),
    ):
        try:
            t = attempt()
            if t:
                return str(t)[:4000]
        except Exception:
            continue
    return ""


def _html_of(page):
    for attr in ("html_content", "body", "content"):
        v = getattr(page, attr, None)
        if v:
            return v if isinstance(v, str) else str(v)
    try:
        return str(page)
    except Exception:
        return ""


def try_stealthy(url):
    from scrapling.fetchers import StealthyFetcher
    page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=60000)
    return page, "StealthyFetcher"


def try_plain(url):
    from scrapling.fetchers import Fetcher
    try:
        page = Fetcher.get(url, stealthy_headers=True, timeout=60)
    except TypeError:
        page = Fetcher.get(url)
    return page, "Fetcher"


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "note": "usage: python fetch.py <URL>"}))
        return
    url = sys.argv[1]
    page = None
    used = ""
    errors = []
    for fn in (try_stealthy, try_plain):
        try:
            page, used = fn(url)
            log("fetched via", used)
            break
        except Exception as e:
            errors.append("%s: %s" % (fn.__name__, e))
            log("fetcher failed", fn.__name__, e)
    if page is None:
        print(json.dumps({"ok": False, "url": url, "note": " | ".join(errors)}, ensure_ascii=False))
        return

    html = _html_of(page)
    text_excerpt = _safe_text(page)
    meta = extract(html or "")
    post_text = meta["og_description"] or meta["jsonld_text"] or meta["meta_description"]
    ok = bool(post_text or text_excerpt)
    status = getattr(page, "status", None)
    print(json.dumps({
        "ok": ok,
        "url": url,
        "fetcher": used,
        "status": status,
        "og_title": meta["og_title"],
        "og_description": meta["og_description"],
        "jsonld_text": meta["jsonld_text"],
        "meta_description": meta["meta_description"],
        "post_text": post_text,
        "text_excerpt": text_excerpt,
        "note": "" if ok else "no extractable text; ask user to paste the post body",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
