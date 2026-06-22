# World Cup 2026 — Family Dashboard

Status: Active (building)
Goal: 一個全家三地（Sheffield／香港／三藩市）都開得到嘅 World Cup 2026 dashboard — 自動更新賽果、積分、淘汰賽晉級，可以一齊 star 心水隊。
Key dates: 2026-06-11 → 賽事開始 · 2026-07-19 → 決賽
Owner: Nam
Skills used: —

---

## 點行（本機測試）

```bash
cd projects/PERSONAL/worldcup
pip install -r requirements.txt
streamlit run app.py
```

**唔使任何 API key、唔使登記。** 數據嚟自 openfootball 公開域 JSON（無流量限制），
有齊 104 場真實賽程 + UTC 開賽時間，比數同積分隨賽事自動更新（每半個鐘）。
連唔到網時自動用本機備份 `schedule_2026.json`。

## 數據來源

[openfootball/worldcup.json](https://github.com/openfootball/worldcup.json)（CC0 公開域）。
比數係賽後由社群更新，唔係逐分鐘 live；對家庭睇波台足夠。

## 架構

| 檔案 | 做咩 |
|---|---|
| `app.py` | 主 dashboard（4 個 tab：賽程／積分榜／淘汰賽／心水隊）|
| `api.py` | openfootball 數據連接 + cache + 本機備份 fallback + 積分自動計算 |
| `bracket.py` | 淘汰賽鬼腳圖：placeholder 解析（組首組次／勝負方）+ 生成 PNG（中文隊名、⭐心水隊突出）|
| `stars.py` | 全家共享心水隊（v1 本機 JSON；Phase 2 換 Google Sheet）|
| `schedule_2026.json` | 本機備份賽程（拎唔到網時用）|
| `packages.txt` | Streamlit Cloud 裝中文字型（fonts-noto-cjk），令 PNG 中文唔變空格 |

## 上線 + 待辦（roadmap）

- [x] 手機為主 readable UI + 三地時區 + 積分榜 + star UI
- [x] 接真實免費數據（openfootball，無 key）+ 本機備份 fallback
- [x] 推上 Streamlit Community Cloud，公開連結畀家人
- [x] 全家共享 star（Gist 後端，跨重啟保留）
- [x] 淘汰賽鬼腳圖 PNG（Google 卡式、賽日、中文隊名、48 國旗、⭐ 突出；自動由 live data 填隊）
- [ ] 最佳第三名官方分配對照表（補咗第三名 slot 可更早自動解析；未補前等 openfootball 填真隊名）

### 鬼腳圖點運作
`bracket.py` 每次開頁由 live 數據即時畫：組賽一完 → 出組首組次（用我哋自己算嘅積分榜）；
淘汰賽逐場入結果 → 自動填上勝方，無需人手 push。**唯一限制**：12 隊「最佳第三名」嘅
官方分配對照表未做，所以第三名 slot 會等 openfootball 自己填上真隊名先顯示（之前顯示
「第三名 A/B/C/D/F」combo）。

資料來源核對日：2026-06-15 · [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json)

### 棄用紀錄
API-Football 免費版實測封鎖 2026 季度（只開放 2022–2024），故棄用。
`.streamlit/secrets.toml` 入面嗰條 key 已唔再需要（保留無害，已 git-ignore）。
