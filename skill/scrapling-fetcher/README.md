# scrapling-fetcher — Mode B 取文容器

把社群貼文 URL 取成純文字,供 `dissecting-paper-hype` 的 **Mode B 快篩模式**使用。
用 Docker 封裝 Scrapling(Python 自適應爬蟲,處理 JS 動態載入/反爬),避免在 Windows 本機裝 Python 3.10+/Playwright 的重依賴。

## 建置(一次)
```
# 在本資料夾(scrapling-fetcher/)下執行:
docker build -t hype-fetcher .
```

## 取文
```
docker run --rm hype-fetcher "https://www.threads.net/@user/post/XXXX"
```
stdout 是單一 JSON 物件,關鍵欄位:
- `ok` — 是否抓到可用文字。`false` → skill 改請使用者貼上內文。
- `post_text` — 最佳猜測的貼文內文(優先 og:description → JSON-LD → meta description)。
- `og_title` / `og_description` / `jsonld_text` / `text_excerpt` — 備援欄位。
- `fetcher` — 實際用了 `StealthyFetcher`(跑 JS)或退路 `Fetcher`(httpx)。
- `note` — 失敗原因。

## 實測結果(2026-06,首次建置即通過)
- ✅ **真實公開 Threads 貼文**(`threads.com/@sung.kim.mw/post/DTafy6wEe19`,分享 Sakana DroPE 論文):`ok:true`,`StealthyFetcher`(camoufox 跑 JS)抓到**完整正文** + 引用連結;`text_excerpt` 含貼文全文(夾雜導覽列雜訊,屬正常)。
- ✅ **arXiv abs 頁**:`ok:true`,og_title + 摘要正確。
- ✅ **端到端**:抓回的 Threads 內文丟進 Mode B → 自動 WebFetch 查證所引 arXiv → 評 12/100 🟢(正確判為誠實分享)。

## 設計與限制(誠實話)
- **`text_excerpt` 是主力**:StealthyFetcher 跑完 JS 後的可見文字,Threads 正文通常完整落在這裡;`post_text`(og:description)有時只含部分(如只有「Paper:/Blog:」那段),所以 skill 端應**兩者都看**。
- **`text_excerpt` 夾雜雜訊**:含 Home/Search/Notifications 等導覽列與「Related threads」其他貼文;拆解時挑出真正貼文段落即可,MVP 不另做清洗。
- **第一次 build 的雷**:`pip install scrapling` 不含取文相依(缺 `curl_cffi`),必須 `pip install "scrapling[fetchers]"` 再 `scrapling install` 下載瀏覽器——Dockerfile 已修正。
- **X(Twitter)登入牆重**:多數推文未登入抓不到完整內文,常只剩殘缺 og 或被導登入頁(本批未實測到成功案例);此時 `post_text` 殘缺 → 改請使用者貼上。
- 本容器**只負責取文**,不做評分;評分/查證在 skill 的 Mode B pipeline。
- 取文是可替換 adapter:不想用 Docker 時,直接請使用者貼上內文即可,後續 pipeline 完全相同。

## 疑難
- `docker ps` 報 daemon 未啟動 → 先開 Docker Desktop。
- 抓不到任何文字 → 正常退場,改用貼上模式;不要對殘缺內容硬評分。
