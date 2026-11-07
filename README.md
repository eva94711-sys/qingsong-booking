# 青松物理治療所 LINE LIFF 智能預約掛號與門診管理系統

專為高雄市鳥松區 **青松物理治療所** 量身打造之 LINE LIFF 預約掛號、時段防衝堂、24 小時自動確認出席與診所門診營運後台系統。

---

## 🌟 系統核心特色

1. **LINE LIFF 極速原生體驗**：
   - 病患於青松 LINE 官方帳號（`@126cxeyj`）點擊圖文選單即可秒開。
   - 免註冊、免密碼，自動取得 LINE User ID 並記憶病患基本資料（姓名、生日、電話）。
   - 兼顧外部瀏覽器相容性，內建優雅的 LINE 帳號模擬器，方便測試不同病患身份。

2. **全所兩位專業治療師配置**：
   - **01 劉韋綸 院長／所長**：專精骨骼肌肉徒手物理治療、肌肉動作控制、銀髮族運動訓練、肌筋膜疼痛處理。
   - **02 洪嘉良 物理治療師**：專精皮拉提斯器械、肌肉骨骼、術後復健、內臟筋膜與疤痕手療。
   - 支援病患指定個別治療師或選擇「不指定（由診所安排空檔治療師）」。

3. **智慧防衝堂與時段鎖定**：
   - 開放未來 30 天內固定時段預約。
   - 預約時透過交易級排他鎖，已被他人預約或已額滿之時段自動鎖定反灰，徹底杜絕重複預約。

4. **就診前 24 小時動態出席確認推播**：
   - 系統依每位病患的看診時間，精準於 24 小時前發送 LINE Flex 互動卡片。
   - 附帶「✅ 會準時前往」與「❌ 無法前往/取消」按鈕。
   - 若病患點擊取消，**系統即刻自動釋放該時段**供其他病患預約掛號。
   - 若就診前仍未回覆，後台即時以橘黃色「待確認」高亮標示，方便櫃檯人員主動電話關懷。

5. **現代化診所營運管理後台 (`/admin`)**：
   - 支援電腦與手機瀏覽器登入。
   - 即時儀表板：有效預約數、今日看診數、已確認數、24H待確認數、已取消數。
   - 預約日程名冊（支援日期、治療師、出席狀態篩選）。
   - 一鍵匯出 CSV / Excel 報表。
   - 支援櫃檯現場／電話手動新增掛號。

---

## 📱 病患端 5 大核心分頁 (`/`)

* **分頁 1：預約掛號**
  * 步驟 1：選擇就診類型（初診勾選轉診單／複診／肌力訓練免單）與選擇治療師。
  * 步驟 2：選取日期（30天滾動日曆）與時段（實時防衝堂）。
  * 步驟 3：填寫基本資料（支援 LINE UID 自動記憶帶入）。
  * 步驟 4：確認須知與送出掛號，顯示精美成功憑證。
* **分頁 2：治療師團隊**
  * 劉韋綸院長、洪嘉良治療師完整經歷、專長與證照介紹，附一鍵指定預約捷徑。
* **分頁 3：服務收費一覽**
  * 整體評估治療 ($1,500)、局部評估 ($600-800)、院長指定門診 ($2,000)、體外震波 ($1,000)、高齡肌力訓練 ($3,000) 費率與說明。
* **分頁 4：診所簡介與注意事項**
  * 地址（高雄市鳥松區華美路69號）、Google 地圖導航、一鍵撥號（07-7353353）、營業時間、完全預約制與穿著寬鬆衣物等注意事項。
* **分頁 5：我的預約**
  * 查詢個人預約紀錄、出席狀態徽章（綠色已確認、橘色待確認、紅色已取消），並可在看診前 24 小時前線上取消。

---

## 🚀 本機快速啟動（零外部依賴）

本系統採用標準 Python 3 與 SQLite 打造，**無須執行繁瑣的 npm install 或 pip 安裝**，隨開即用！

```bash
cd /Users/minzhen/.gemini/antigravity/scratch/qingsong-pt-booking

# 啟動本機伺服器
python3 server.py
```

終端機輸出：
```text
🌲 青松物理治療所預約系統伺服器已啟動: http://localhost:8080
📱 病患端 LINE LIFF 體驗: http://localhost:8080/
🖥 診所端管理後台: http://localhost:8080/admin
```

開啟瀏覽器造訪：
* 病患端預約頁面：`http://localhost:8080/`
* 診所管理後台：`http://localhost:8080/admin`

---

## 🔧 LINE LIFF 與 Messaging API 上線設定

### 1. LINE Developers Console 設定
1. 前往 [LINE Developers Console](https://developers.line.biz/)。
2. 進入青松物理治療所的 Provider 與 Messaging API Channel。
3. 建立一個 **LIFF App**：
   - **LIFF app name**：青松物理治療所線上預約
   - **Size**：Full
   - **Endpoint URL**：填入部署後的正式網址（例如：`https://your-domain.vercel.app/`）
   - **Scope**：勾選 `profile`、`openid`
   - **Bot link feature**：On (Normal)
4. 取得之 **LIFF ID**（系統預設已設定為您提供的 `2012064889-uSjEJVic`）。

### 2. LINE Webhook 串接（自動接收出席確認）
1. 在 Messaging API 設定中，將 **Webhook URL** 設為：
   `https://your-domain.vercel.app/api/line/webhook`
2. 開啟 **Use webhook**。
3. 當病患在 LINE 聊天室點擊「✅ 會準時前往」或「❌ 無法前往/取消」時，系統即自動同步更新資料庫狀態！

### 3. Vercel 免費一鍵部署與 Cron 排程
1. 將此專案資料夾推送到 GitHub。
2. 在 [Vercel](https://vercel.com/) 點擊 **Import Project**。
3. 本專案已內建 `vercel.json`，自動啟用 Vercel Cron 每小時自動檢查並發送就診前 24 小時的 LINE 出席確認推播。

---

## 📂 專案檔案結構

```text
qingsong-pt-booking/
├── server.py              # 後端 REST API 伺服器與 LINE Webhook / 24H 排程
├── database.py            # SQLite 資料庫架構、種子資料（劉院長、洪治療師、預設排程）
├── vercel.json            # Vercel 部署設定與 Vercel Cron 排程
├── README.md              # 系統完整說明文件
├── data/
│   └── qingsong.db        # SQLite 門診預約資料庫
└── public/
    ├── index.html         # 病患端 LINE LIFF 應用程式（5 大分頁）
    ├── admin.html         # 診所端管理後台（日曆、排班、狀態監控、CSV 匯出）
    ├── js/
    │   └── app.js         # 前端預約防衝堂、LIFF 初始化、病患資料記憶邏輯
    └── images/
        ├── therapist_liu.svg   # 01 劉韋綸 院長頭像
        └── therapist_hong.png  # 02 洪嘉良 物理治療師照片
```

---

*青松物理治療所 · 專業· 溫暖 · 動作重塑*
