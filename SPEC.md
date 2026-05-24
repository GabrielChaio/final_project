# 踩地雷遊戲 — 開發者規格文件

## 目錄

1. [專案概覽](#1-專案概覽)
2. [技術棧與相依套件](#2-技術棧與相依套件)
3. [架構設計](#3-架構設計)
4. [類別與函式規格](#4-類別與函式規格)
   - [center_window](#41-center_window)
   - [account.py](#42-accountpy本機帳號模組)
   - [firebase_client.py](#43-firebase_clientpyfirebase-rest-api-封裝模組)
   - [MinesweeperLogic](#44-minesweeperlogic)
   - [GameSettingsDialog](#45-gamesettingsdialog)
   - [MinesweeperUI](#46-minesweeperui)
   - [LeaderboardWindow](#47-leaderboardwindow)
   - [ReplayListWindow](#48-replaylistwindow)
   - [LoginWindow](#49-loginwindow)
   - [RegisterWindow](#410-registerwindow)
   - [RecoveryKeyDialog](#411-recoverykeydialog)
   - [MainMenu](#412-mainmenu)
5. [遊戲邏輯規則](#5-遊戲邏輯規則)
6. [資料結構](#6-資料結構)
7. [事件流程](#7-事件流程)
8. [音效與資源管理](#8-音效與資源管理)
9. [打包與發布](#9-打包與發布)
10. [已知限制與預留功能](#10-已知限制與預留功能)

---

## 1. 專案概覽

| 項目 | 內容 |
|------|------|
| 程式語言 | Python 3.11 |
| 主程式 | `MinesweeperGameUI.py` |
| UI 框架 | tkinter（標準函式庫） |
| 音效引擎 | pygame.mixer |
| 圖片處理 | Pillow（PIL） |
| 雲端資料庫 | Firebase Realtime Database（REST API） |
| 本機帳號 | `account.json`（玩家 ID、顏色、Recovery Key） |
| 執行環境 | 桌面視窗應用程式（Windows 為主） |

---

## 2. 技術棧與相依套件

```
pillow    # 主選單背景圖片的載入與縮放
pygame    # 背景音樂與音效播放
requests  # Firebase Realtime Database REST API 呼叫
tkinter   # 視窗、元件、對話框（Python 標準函式庫，無需安裝）
hashlib   # SHA-256 雜湊 Recovery Key（Python 標準函式庫）
secrets   # 密碼學安全亂數，用於產生 Recovery Key（Python 標準函式庫）
pathlib   # 以 .py 檔所在位置為基準的跨平台路徑管理（Python 標準函式庫）
random    # 地雷隨機佈置（Python 標準函式庫）
json      # 帳號本地儲存（Python 標準函式庫）
datetime  # 排行榜日期戳記（Python 標準函式庫）
collections.deque  # BFS 展開與回放歷史（Python 標準函式庫）
```

---

## 3. 架構設計

### 分層架構

```
Firebase Realtime Database（雲端）
    users/{player_id}/          ← 玩家公開資訊（顏色、建立時間）
    auth/{player_id}/           ← 驗證資料（Recovery Key SHA-256 hash）
    leaderboard/{difficulty}/   ← 排行榜條目（含 challenge_type 欄位）
    records/{player_id}/        ← 玩家回放 JSON

account.py（本機帳號模組）
    account.json ← player_id、color、recovery_key（明文，僅本機）

firebase_client.py（REST API 封裝模組，無 UI）
    is_online / user_exists / register_user / verify_login
    upload_score / get_leaderboard
    upload_replay / get_replay_list / delete_replay

MinesweeperGameUI.py（主程式）
MainMenu（tk.Tk）
│  主視窗，管理帳號狀態（self.account）與畫面切換
│
├── LoginWindow（tk.Toplevel）       ← 登入視窗
├── RegisterWindow（tk.Toplevel）    ← 註冊視窗（ID + 顏色）
├── RecoveryKeyDialog（tk.Toplevel） ← 一次性 Recovery Key 顯示
├── GameSettingsDialog（tk.Toplevel）← 遊戲參數設定
│
├── MinesweeperUI（tk.Frame）
│       遊戲主介面，持有 main_app 參考以存取帳號
│       ├── MinesweeperLogic  ← 純邏輯層（無 UI 元件）
│       └── 操作歷史 history（list）← 回放資料來源
│
├── LeaderboardWindow（tk.Toplevel）
│       排行榜查詢視窗，呼叫 firebase_client.get_leaderboard()
│
└── ReplayListWindow（tk.Toplevel）
        回放清單視窗，呼叫 firebase_client.get_replay_list()
```

### 關係說明

- `MainMenu` 是唯一的頂層視窗（`tk.Tk`），其餘介面皆嵌入其中或以子視窗呈現。
- `MinesweeperLogic` 不持有任何 tkinter 物件，可獨立測試。
- `MinesweeperUI` 持有 `MinesweeperLogic` 的參考，並持有 `main_app`（`MainMenu`）參考以存取帳號與開啟登入視窗。
- 遊戲結束後，`MinesweeperUI` 呼叫 `on_close_callback`（即 `MainMenu.show_main_menu`）回到主選單。
- 所有雲端操作皆透過 `firebase_client` 模組進行，超時設定 6 秒；`is_online()` 超時 3 秒。

---

## 4. 類別與函式規格

### 4.1 `center_window`


```python
def center_window(window)
```

**用途**：將任意 tkinter 視窗置中於螢幕。

**流程**：
1. 呼叫 `update_idletasks()` 確保視窗尺寸已計算完成。
2. 讀取視窗寬高與螢幕解析度。
3. 以 `geometry('+x+y')` 設定視窗位置。

**使用位置**：`GameSettingsDialog.__init__`、`MainMenu.__init__`、`MinesweeperUI.show_custom_end_dialog`、`MainMenu.start_game`、`LeaderboardWindow.__init__`

---

### 4.2 `account.py`（本機帳號模組）

**職責**：管理 `account.json`（本機帳號）的讀寫、Recovery Key 的產生與 SHA-256 雜湊。

#### 常數

| 常數 | 說明 |
|------|------|
| `ACCOUNT_FILE` | `Path(__file__).resolve().parent / "account.json"` |
| `_CHARS` | Recovery Key 字元集：`A-Z + 2-9`，排除易混淆字元 `0 O 1 I L`（共 31 字元） |

#### 函式

| 函式 | 說明 |
|------|------|
| `generate_recovery_key() → str` | 以 `secrets.choice` 產生 4 段各 4 字元的 Recovery Key，格式 `XXXX-XXXX-XXXX-XXXX` |
| `hash_key(key: str) → str` | strip + upper 後計算 SHA-256 hex digest |
| `load() → dict \| None` | 讀取 `account.json`；不存在或缺少必要欄位時回傳 `None` |
| `save(player_id, color, recovery_key) → dict` | 寫入 `account.json` 並回傳 dict |

#### `account.json` 格式

```json
{
  "player_id": "Alice",
  "color":    "#cc0000",
  "recovery_key": "AB3D-EF4G-HJ5K-MN6P"
}
```

> Recovery Key 明文存本機（本機為信任裝置），雲端 Firebase 只存 SHA-256 hash。

---

### 4.3 `firebase_client.py`（Firebase REST API 封裝模組）

**職責**：封裝所有 Firebase Realtime Database REST 操作，以及帳號驗證、排行榜、回放的高階業務函式。

#### 常數

| 常數 | 說明 |
|------|------|
| `FIREBASE_URL` | Firebase 資料庫根 URL |
| `_TIMEOUT` | 一般請求超時秒數（6 秒） |

#### 基礎 REST 函式

| 函式 | 說明 |
|------|------|
| `_get_raw(path) → (bool, any)` | GET 並回傳 `(ok, data)`；`ok=True` 時 `data` 為 JSON 內容（路徑不存在為 `None`）；`ok=False` 時 `data` 為 HTTP 狀態碼整數（伺服器有回應）或 `None`（網路異常） |
| `_put(path, data) → bool` | PUT，回傳是否成功 |
| `_post(path, data) → str \| None` | POST（Firebase push），回傳新節點 key 或 None |
| `_delete(path) → bool` | DELETE，回傳是否成功 |
| `is_online() → bool` | 以 GET `/.json?shallow=true` 快速探測連線（超時 3 秒）；收到任何 HTTP 回應（含 403）即視為在線，僅網路例外（逾時、DNS 錯誤）才回傳 `False` |

#### 帳號操作

| 函式 | 說明 |
|------|------|
| `user_exists(player_id) → bool \| None` | `True`=存在，`False`=不存在，`None`=網路錯誤 |
| `register_user(player_id, color, hash) → (bool, str \| None)` | 先查重，再同時寫 `users/{pid}` 與 `auth/{pid}`；回傳 `(成功, 錯誤訊息)` |
| `verify_login(player_id, hash) → (bool, str)` | 讀 `users/{pid}` 驗存在、讀 `auth/{pid}` 比對 hash；成功回傳 `(True, color)`，失敗回傳 `(False, 錯誤訊息)`；若 `auth/` 回傳 HTTP 401/403 則提示「Firebase 安全規則未開放 auth/ 讀取」 |

#### Firebase 資料結構

```
users/{player_id}/
    color:      "#cc0000"
    created_at: "2026-05-24T10:00:00"

auth/{player_id}/
    recovery_key_hash: "sha256hex..."

leaderboard/{difficulty}/{entry_id}/
    player_id:      "Alice"
    player_color:   "#cc0000"
    time_sec:       12.345
    date:           "2026-05-24"
    challenge_type: "unlimited" | "no_item" | "no_item_no_flag"
    replay:         （完整回放 JSON，嵌入於條目中，供排行榜回放使用）

records/{player_id}/{record_id}/
    （完整回放 JSON，格式同下方 4.4 節；由「儲存遊戲紀錄」上傳，與排行榜獨立）
```

> **回放資料獨立原則**：排行榜條目直接嵌入 `replay` 欄位；`records/` 為玩家個人紀錄。兩者無交叉依賴，刪除個人紀錄不影響排行榜回放。

#### Security Rules

```json
{
  "rules": {
    "users":       { "$pid": { ".read": true, ".write": "!data.exists()" } },
    "auth":        { "$pid": { ".read": true, ".write": "!data.exists()" } },
    "leaderboard": { ".read": true, ".write": true },
    "records":     { "$pid": { ".read": true, ".write": true } }
  }
}
```

#### 排行榜操作

| 函式 | 說明 |
|------|------|
| `upload_score(difficulty, player_id, player_color, time_sec, challenge_type, replay_data=None) → bool` | POST 至 `leaderboard/{difficulty}`；若提供 `replay_data` 則直接嵌入條目的 `replay` 欄位 |
| `get_leaderboard(difficulty, challenge_type) → list \| None` | GET 全部條目後客戶端過濾 challenge_type，依 time_sec 排序後取前 10；網路錯誤回傳 None，空榜回傳 [] |

> 一局符合資格的勝利最多上傳 3 筆（`unlimited` 必傳；無道具再傳 `no_item`；無道具無旗子再傳 `no_item_no_flag`）。每筆條目各自嵌入一份回放資料。

#### 排行榜鍵值對照

| 難度顯示 | Firebase path | 挑戰類型顯示 | challenge_type |
|----------|--------------|--------------|----------------|
| 簡單 | `easy` | 無限制 | `unlimited` |
| 普通 | `normal` | 無道具 | `no_item` |
| 困難 | `hard` | 無道具無旗子 | `no_item_no_flag` |

#### 回放操作

| 函式 | 說明 |
|------|------|
| `upload_replay(player_id, replay_data) → str \| None` | POST 至 `records/{player_id}`，回傳新節點 key 或 None |
| `get_replay_list(player_id) → list \| None` | GET `records/{player_id}` 後解析 meta，依日期由新到舊排序；網路錯誤回傳 None，無記錄回傳 [] |
| `delete_replay(player_id, record_id) → bool` | DELETE `records/{player_id}/{record_id}` |
| `get_replay_by_id(player_id, record_id) → dict \| None` | GET `records/{player_id}/{record_id}`，成功回傳 dict，失敗或不存在回傳 None |

#### 回放 JSON 格式（存於 Firebase）

```json
{
  "version": 1,
  "meta": {
    "player_id":    "Alice",
    "player_color": "#cc0000",
    "result":       "win",
    "date":         "2026-05-24 10:00:00",
    "time_sec":     12.345,
    "difficulty":   "easy"
  },
  "settings": { "rows": 8, "cols": 8, "mines": 10, "radar_uses": 2 },
  "board":   [[-1, 0, ...], ...],
  "history": [["click", 3, 4, 0.0], ["flag", 1, 2, 1.234], ...]
}
```

> `board` 儲存完整盤面，回放時直接指定 `logic.board = data["board"]` 並設 `logic.first_click = False`，不呼叫 `reset_board()`。`history` 中 tuple 序列化為 list，讀取後以 `tuple()` 還原。

---

### 4.4 `MinesweeperLogic`

**職責**：管理遊戲盤面狀態，不含任何 UI 邏輯。

#### 建構子

```python
def __init__(self, rows: int, cols: int, mines: int)
```

| 屬性 | 型別 | 說明 |
|------|------|------|
| `rows` | int | 盤面列數 |
| `cols` | int | 盤面行數 |
| `mines_count` | int | 地雷總數 |
| `board` | list[list[int]] | 盤面數值（-1 為地雷，0–8 為周圍地雷數） |
| `revealed` | list[list[bool]] | 各格翻開狀態 |
| `first_click` | bool | 是否為本局第一次點擊 |

> **注意**：`board` 與 `revealed` 在建構子中為空列表，須等到 `reset_board()` 呼叫後才會初始化。此設計讓地雷在第一次點擊後才生成，確保首格安全。

#### `reset_board(start_r, start_c)`

**觸發時機**：玩家第一次左鍵點擊時呼叫。

**演算法**：
1. 初始化 `board`（全 0）與 `revealed`（全 False）。
2. 計算禁區 `forbidden`：以 `(start_r, start_c)` 為中心的 3×3 範圍（共最多 9 格）。
3. 隨機佈置地雷，跳過禁區與已有地雷的格子。
4. 對每個非地雷格計算周圍 8 格的地雷數，寫入 `board`。

**保證**：玩家第一格點擊的周圍 3×3 範圍內不含地雷。

#### `get_revealed_count() → int`

回傳目前已翻開的格子總數，供 `check_win()` 判斷勝利條件使用。

---

### 4.5 `GameSettingsDialog`

```python
class GameSettingsDialog(tk.Toplevel)
```

**職責**：以模態對話框收集遊戲參數，結果存於 `self.result`。

#### 建構子參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `parent` | tk.Widget | — | 父視窗 |
| `default_r` | int | 8 | 預設列數 |
| `default_c` | int | 8 | 預設行數 |
| `default_m` | int | 8 | 預設地雷數 |
| `is_custom` | bool | False | 是否顯示自訂輸入欄位（列數、行數、地雷數、探測次數） |
| `default_id` | str | `"Unknown"` | 備用玩家 ID（`show_player_fields=False` 時直接使用，不顯示輸入框） |
| `default_color` | str | `"#000000"` | 備用 ID 顏色（`show_player_fields=False` 時直接使用） |
| `show_player_fields` | bool | True | 是否顯示「玩家 ID」與「ID 顏色」欄位；自訂模式傳入 `False` 以隱藏這兩個欄位 |

> **使用情境**：非自訂難度（簡單 / 普通 / 困難）點擊後直接呼叫 `start_game()`，完全不開啟此對話框。自訂模式開啟對話框時傳入 `show_player_fields=False`，玩家 ID 與顏色由帳號自動帶入。

#### 靜態方法

| 方法 | 說明 |
|------|------|
| `_darken_if_bright(hex_color, threshold=0.7) → str` | 計算感知亮度 `(0.299R + 0.587G + 0.114B) / 255`；若超過 `threshold` 則等比縮放 RGB 至 `threshold / brightness`，回傳調暗後的 HEX 色碼，否則原色回傳 |

#### 輸出格式

```python
self.result = (rows, cols, mines, player_id, player_color, radar_uses)
# 型別：(int, int, int, str, str, int)
# player_color 為 HEX 色碼字串，例如 "#ff0000"
```

#### 驗證規則（自訂模式）

| 欄位 | 限制 | 錯誤訊息 |
|------|------|----------|
| 列數 | 5 ≤ 值 ≤ 27 | 「列數超出範圍 (5-27)」 |
| 行數 | 5 ≤ 值 ≤ 44 | 「行數超出範圍 (5-44)」 |
| 地雷數 | `int(列 × 行 × 0.1)` ≤ 值 ≤ `int(列 × 行 × 0.25)` | 「地雷數量必須在 N 到 M 之間」 |
| 探測次數 | 值 ≥ 0 | 「探測次數不能為負數」 |

> **尺寸下限說明**：最小 5×5 可避免首點 3×3 禁區覆蓋全圖，確保地雷有位置可放。
> **上限說明**：列 27、行 44 為實測在一般螢幕（1920×1080）下不超出可視範圍的最大值。
> **地雷密度範圍說明**：上限 25% 可確保地圖生成幾乎不會超過 1000 次嘗試；下限 10% 可避免首次展開後幾乎直接通關的情況。兩個閾值皆以實測為基礎。

#### 動態地雷數量標籤

自訂模式下，列數與行數輸入框綁定 `<KeyRelease>` 事件，呼叫 `_update_mine_range_label()`，即時以 `地雷數量 (2-{max_m}):` 格式更新標籤。

驗證失敗時以 `messagebox.showerror` 顯示錯誤訊息，對話框不關閉。

---

### 4.6 `MinesweeperUI`

```python
class MinesweeperUI(tk.Frame)
```

**職責**：遊戲主介面，處理所有玩家輸入、畫面更新、道具使用與回放。

#### 建構子參數

| 參數 | 說明 |
|------|------|
| `parent` | 父視窗（即 `MainMenu` 實例） |
| `logic` | `MinesweeperLogic` 實例 |
| `player_id` | 玩家顯示名稱 |
| `player_color` | 玩家名稱顯示顏色（HEX） |
| `radar_uses` | 金屬探測器初始使用次數 |
| `on_close_callback` | 離開遊戲時呼叫的回呼函式 |

#### 重要屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `buttons` | list[list[tk.Button]] | 對應盤面的按鈕二維陣列 |
| `history` | list[tuple] | 操作歷史，格式見下方 |
| `radar_mines` | set[tuple[int,int]] | 探測器已揭示為地雷的格子座標集合，禁止後續左右鍵操作 |
| `flag_count` | int | 目前已插旗格子數，用於計算剩餘地雷顯示（可為負值） |
| `radar_used_count` | int | 本局累計使用探測器次數；0 表示符合無道具榜資格 |
| `flag_used_count` | int | 本局曾插旗次數（取消後仍計）；0 表示符合無道具無旗子榜資格 |
| `elapsed_time` | float | 遊戲結束時的精確耗時（秒，3 位小數）；遊戲結束前為 `0.0` |
| `_start_ts` | float | `time.monotonic()` 起始時間戳，首次點擊時設定 |
| `timer_running` | bool | 計時器是否運行中 |
| `is_replaying` | bool | 是否處於回放模式 |
| `radar_uses_left` | int | 金屬探測器剩餘次數 |
| `radar_type` | tk.StringVar | 目前選擇的探測模式（`"none"` / `"cross"` / `"area"`） |
| `_replay_index` | int | 下一個待執行的 history 步驟索引 |
| `_replay_paused` | bool | 回放是否處於暫停狀態 |
| `_replay_speed` | float | 目前回放速度倍率（0.5 / 1.0 / 2.0 / 3.0） |
| `_replay_game_base` | float | 上次凍結時的遊戲時間（秒），作為插值計算基準 |
| `_replay_wall_ref` | float | `_replay_game_base` 對應的 wall clock 時間點 |
| `_replay_total_dur` | float | 回放總時長（秒），取自 `history[-1][-1]` |
| `_replay_slider_busy` | bool | 程式內部更新滑塊時的防重入旗標，避免觸發 seek 回呼 |
| `_replay_after_id` | str\|None | `after()` 排程 ID，暫停或 seek 時用於取消待執行的 `replay_step` |
| `btn_pause` | tk.Button | 暫停/繼續/返回按鈕（回放結束後顯示「返回」） |
| `btn_prev` | tk.Button | 上一步按鈕（僅暫停時啟用） |
| `btn_next` | tk.Button | 下一步按鈕（僅暫停且未結束時啟用） |
| `replay_slider` | tk.Scale | 時間軸滑塊（0 至 `_replay_total_dur`，解析度 0.001 秒） |

#### 操作歷史格式（`history`）

```python
('click',       row, col,        t)  # 左鍵點擊
('flag',        row, col,        t)  # 右鍵旗標切換
('radar',       row, col, mode,  t)  # 金屬探測器（mode: "cross" 或 "area"）
('auto_reveal', row, col,        t)  # 雙擊左鍵自動翻開周圍格
```

`t` 為 `_elapsed()` 回傳值（float，相對於本局首次點擊的秒數，3 位小數）。儲存至 JSON 時 tuple 序列化為 list，`t` 仍為 float，讀取後以 `tuple()` 還原。

#### 主要方法

| 方法 | 說明 |
|------|------|
| `create_widgets()` | 建立頂部資訊列（含剩餘地雷標籤）、工具面板（探測器）、盤面按鈕格 |
| `on_click(r, c, from_replay)` | 左鍵點擊處理；已插旗或探測器地雷格無反應，否則依模式分派至探測器或翻格 |
| `on_right_click(r, c, from_replay)` | 右鍵旗標切換；首格未翻則警告，探測器地雷格與已翻開的格子不可插旗；更新 `flag_count` 與剩餘地雷標籤 |
| `on_double_click(r, c, from_replay)` | 雙擊左鍵快速翻開；對已翻數字格，若周圍標記數等於格子數字則自動翻開剩餘未標記格 |
| `expand(r, c)` | BFS 翻開格子；值為 0 時自動展開相鄰 8 格 |
| `check_win()` | 判斷剩餘未翻格數是否等於地雷數；勝利時呼叫 `end_game_flow(result="win")` |
| `use_radar(r, c, mode)` | 執行探測器效果、更新剩餘次數與剩餘地雷標籤；累計 `radar_used_count` |
| `reveal_radar_cell(nr, nc)` | 揭示單一格：地雷顯示黃底 💣 並加入 `radar_mines`，安全格呼叫 expand |
| `update_mine_count_label()` | 更新剩餘地雷標籤：`mines_count - len(radar_mines) - flag_count` |
| `_elapsed() → float` | 回傳 `round(time.monotonic() - _start_ts, 3)`，即精確耗時（秒） |
| `update_timer()` | 每 1000ms 讀取 monotonic 差值並以整數秒更新標籤 |
| `end_game_flow(message, result="lose")` | 停止計時，若有歷史則呼叫 `_show_end_dialog()` |
| `_show_end_dialog(message, result)` | 顯示遊戲結果與三個按鈕：儲存遊戲紀錄 / 上傳排名（勝利且非自訂時啟用）/ 返回主選單；將按鈕存為 `self._end_btn_save` / `self._end_btn_rank` |
| `_on_save_record(result, dialog)` | 檢查帳號，若未登入先開 LoginWindow，登入後呼叫 `_do_save_record` |
| `_do_save_record(result, dialog)` | 呼叫 `fb.upload_replay()` 上傳至 `records/{player_id}/`；成功後禁用 `_end_btn_save` 防止重複上傳 |
| `_on_upload_rank(difficulty, dialog)` | 檢查帳號，若未登入先開 LoginWindow，登入後呼叫 `_do_upload_rank` |
| `_do_upload_rank(difficulty, dialog)` | 呼叫 `_build_replay_data("win")` 建立回放，依 `radar_used_count` / `flag_used_count` 判定資格，呼叫 `fb.upload_score()` 上傳（回放直接嵌入排行榜條目）；成功後禁用 `_end_btn_rank` |
| `_build_replay_data(result) → dict` | 封裝 version、meta、settings（`radar_uses = 剩餘次數 + 已用次數`）、board、history（tuple → list）為回放 dict |
| `start_replay(history=None)` | 若傳入 `history` 則覆蓋 `self.history`；重置盤面視覺與回放狀態，在盤面下方建立控制列（暫停/繼續、倍速、上一步、下一步、時間軸滑塊），初始為暫停狀態 |
| `_execute_replay_record(record)` | 執行單一 history 紀錄（不更新 index 或時間戳），供 `replay_step` / `_replay_next` / `_seek_to_index` 共用 |
| `_replay_smooth_tick()` | 每 200ms 根據 wall clock × 速度插值更新 `timer_label` 與滑塊；暫停或回放結束時自動停止 |
| `replay_step()` | 逐步重播：以 `_replay_index` 驅動，依相鄰步驟時間戳差值（floor 1ms，無上限，除以速度倍率）排程下一步 |
| `_seek_to_index(n)` | 同步 seek 至「最後執行步驟 = n」的盤面狀態，維持暫停（n=-1 代表回到初始狀態） |
| `_seek_to_time(target_time)` | 以目標時間（秒）為目標，二分搜尋最近步驟後呼叫 `_seek_to_index` |
| `_update_replay_buttons()` | 根據目前狀態更新四個控制元件的文字與啟用狀態 |
| `_toggle_replay_pause()` | 切換暫停/繼續；回放結束後按鈕文字變為「返回」，點擊時呼叫 `exit_game()` |
| `_on_speed_change(*_)` | 速度選單回呼；切速時凍結目前遊戲時間基準（`_replay_game_base`）避免時間跳躍 |
| `_replay_prev()` | 暫停狀態下回退一步（`_seek_to_index(max(-1, index - 2))`） |
| `_replay_next()` | 暫停狀態下前進一步 |
| `_on_slider_press(event)` | 滑鼠按下滑塊時自動暫停並凍結時間基準 |
| `_on_slider_release(event)` | 滑鼠放開滑塊時呼叫 `_seek_to_time(slider.get())` |
| `_on_slider_cmd(value)` | 刻意保留為空函式；seek 僅在放開滑鼠時觸發，拖移中不更新畫面 |
| `exit_game()` | 停止音樂、銷毀 Frame、執行回呼函式 |

#### 探測器模式行為

| `radar_type` 值 | 揭示範圍 |
|----------------|----------|
| `"cross"` | 目標格所在的整列（所有 col）＋整行（所有 row） |
| `"area"` | 以目標格為中心的 3×3 九宮格（超出邊界自動截斷） |

#### 格子視覺狀態

| 狀態 | 背景色 | 文字 |
|------|--------|------|
| 未翻開 | SystemButtonFace（系統預設） | 無 |
| 翻開（安全） | `#d1d1d1` | 數字（依值著色，見下表） |
| 探測器揭示（地雷） | `#f1c40f`（黃色） | 💣 |
| 踩雷 | 紅色 | 💣 |
| 插旗 | 不變 | 🚩（紅色） |

數字顏色對應（`disabledforeground`）：

| 值 | 顏色 |
|----|------|
| 1 | blue |
| 2 | green |
| 3 | red |
| 4 | darkblue |
| 5 | darkred |
| 6 | cyan |
| 7 | black |
| 8 | grey |

---

### 4.7 `LeaderboardWindow`

```python
class LeaderboardWindow(tk.Toplevel)
```

**職責**：排行榜查詢視窗，提供難度與挑戰類型篩選、前 10 名成績表格，以及回放任一排名記錄的功能。

#### 建構子

```python
def __init__(self, parent)
```

建立視窗、兩個 `tk.OptionMenu`、`ttk.Treeview`（`selectmode="browse"`）及底部按鈕列（「回放」、「重新整理」），呼叫 `refresh()` 載入初始資料後置中顯示。

#### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `diff_var` | tk.StringVar | 目前選擇的難度（`"簡單"` / `"普通"` / `"困難"`） |
| `cat_var` | tk.StringVar | 目前選擇的挑戰類型 |
| `tree` | ttk.Treeview | 排行榜表格（欄位：排名、玩家 ID、時間、日期；`selectmode="browse"`） |
| `_records` | list[dict] | 目前載入的原始排行榜條目（含 `replay` 欄位） |
| `_parent` | MainMenu | 父視窗參考，用於呼叫 `play_replay()` |

#### 方法

| 方法 | 說明 |
|------|------|
| `refresh()` | 呼叫 `fb.get_leaderboard(diff, cat)` 取雲端資料，刷新 Treeview 並更新 `_records`；網路錯誤時顯示錯誤對話框 |
| `play_selected()` | 取得選取項目對應的 `_records[idx]["replay"]`，驗證格式後銷毀視窗並呼叫 `_parent.play_replay(data)`；不需登入 |

#### OptionMenu 觸發

兩個 OptionMenu 皆綁定 `command=lambda _: self.refresh()`，切換時即時刷新表格。

#### 玩家 ID 顏色顯示

`refresh()` 對每筆記錄取 `player_color`，以 `tag_configure(foreground=color)` 設定 Treeview tag，並在 `insert()` 時套用對應 tag，使 ID 欄位以玩家選擇的顏色呈現。

---

### 4.8 `ReplayListWindow`

```python
class ReplayListWindow(tk.Toplevel)
```

**職責**：顯示登入玩家的雲端回放清單，提供播放、刪除、重新整理功能。

#### 建構子

```python
def __init__(self, parent, account: dict)
```

`account` 為 `MainMenu.account`（含 `player_id`）。建立視窗、`ttk.Treeview`（欄位：玩家、難度、結果、耗時、日期；`selectmode="browse"`）及操作按鈕，呼叫 `refresh()` 載入初始清單後置中顯示。

#### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `tree` | ttk.Treeview | 回放清單表格 |
| `_records` | list[dict] | 目前載入的回放摘要清單（含 `record_id`、`full_data` 等欄位） |

#### 方法

| 方法 | 說明 |
|------|------|
| `refresh()` | 呼叫 `fb.get_replay_list(player_id)` 重新載入；網路錯誤時顯示錯誤對話框；玩家 ID 以其顏色著色 |
| `play_selected()` | 取得選取項目的 `full_data`，驗證格式後呼叫 `_parent.play_replay(data)` |
| `delete_selected()` | 確認後呼叫 `fb.delete_replay()` 刪除並重新整理 |

#### 顯示文字對照

```python
_DIFF_LABEL   = {"easy": "簡單", "normal": "普通", "hard": "困難", "custom": "自訂"}
_RESULT_LABEL = {"win": "勝利", "lose": "失敗"}
```

---

### 4.9 `LoginWindow`

```python
class LoginWindow(tk.Toplevel)
```

**職責**：玩家登入視窗。

#### 建構子

```python
def __init__(self, main_app: MainMenu, on_success=None)
```

顯示玩家 ID 輸入框、Recovery Key 輸入框、「登入」/「取消」按鈕，以及「點此註冊」連結。

#### 行為

- 點擊「登入」：呼叫 `fb.verify_login()`，成功後 `acc.save()` + 更新 `main_app.account` + 呼叫 `on_success` 回呼
- 點擊「點此註冊」：銷毀自身並開啟 `RegisterWindow`（傳遞 `on_success`）

---

### 4.10 `RegisterWindow`

```python
class RegisterWindow(tk.Toplevel)
```

**職責**：帳號註冊視窗（僅含玩家 ID 與顏色欄位）。

#### 行為

1. 點擊「註冊」：呼叫 `acc.generate_recovery_key()` 產生金鑰，再呼叫 `fb.register_user()`
2. 成功後呼叫 `acc.save()` + 更新 `main_app.account`，銷毀自身並開啟 `RecoveryKeyDialog`

---

### 4.11 `RecoveryKeyDialog`

```python
class RecoveryKeyDialog(tk.Toplevel)
```

**職責**：一次性顯示 Recovery Key，提供複製到剪貼簿按鈕與確認關閉按鈕。

關閉後呼叫 `on_close` 回呼（即原始操作的後續流程，如開啟難度選單）。

---

### 4.12 `MainMenu`

```python
class MainMenu(tk.Tk)
```

**職責**：頂層視窗，管理帳號狀態、主選單與難度選擇畫面的切換，以及遊戲的啟動。

#### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `account` | dict \| None | 本機帳號（含 `player_id`、`color`、`recovery_key`）；未登入為 `None` |
| `last_player_id` | str | 本次執行中上一局的玩家 ID（從 account 同步） |
| `last_player_color` | str | 本次執行中上一局的 ID 顏色（從 account 同步） |
| `_status_item` | int \| None | Canvas 登入狀態文字的 item ID |
| `_logout_btn_window` | int \| None | Canvas 登出按鈕的 `create_window` item ID；難度選擇頁不顯示時為 `None` |
| `_current_bgm` | str \| None | 目前播放的背景音樂名稱（`"menu"` 或 `None`）；避免返回主選單時重複重啟音樂 |

#### 方法

| 方法 | 說明 |
|------|------|
| `show_main_menu()` | 顯示主選單（含背景圖、四個選單按鈕、右上角玩家 ID + 登出按鈕）；僅 `_current_bgm != "menu"` 時重新載入播放選單音樂 |
| `show_difficulty_menu()` | 顯示難度選擇（簡單 / 普通 / 困難 / 自訂 + 返回）；右上角顯示玩家 ID 但**不顯示登出按鈕** |
| `_draw_top_bar(show_logout=True)` | 在 Canvas 右上角繪製登入狀態；已登入時玩家 ID 顯示於「登出」按鈕左側（`show_logout=True`）或單獨靠右（`show_logout=False`）；未登入時顯示「未登入」 |
| `_refresh_login_status()` | 更新 `last_player_id`/`last_player_color`，並以 `show_logout=True` 重繪頂部狀態列 |
| `_on_logout()` | 開啟確認登出對話框（含玩家 ID、Recovery Key 顯示、複製按鈕、確認 / 取消） |
| `_do_logout(dlg)` | 關閉對話框、刪除 `account.json`、清空 `self.account`、呼叫 `_refresh_login_status()` |
| `_on_new_game()` | 未登入時開啟登入視窗（callback = `show_difficulty_menu`），否則直接進入難度選擇 |
| `_on_leaderboard()` | 離線時顯示警告並返回；在線時開啟 `LeaderboardWindow` |
| `_on_replay_records()` | 離線時顯示警告並返回；在線且未登入時開啟登入視窗（callback = 開啟 ReplayListWindow）；在線已登入時直接開啟 |
| `show_login_window(callback)` | 建立 `LoginWindow(self, on_success=callback)` |
| `pre_game_setup(r, c, m, is_custom)` | 非自訂模式直接以帳號 ID / 顏色呼叫 `start_game()`；自訂模式開啟 `GameSettingsDialog(show_player_fields=False)` |
| `start_game(r, c, m, p_id, p_color, radar_uses)` | 停止音樂（`_current_bgm = None`）、銷毀主選單容器、建立遊戲介面 |
| `play_replay(data)` | 停止音樂（`_current_bgm = None`）、從回放 dict 建立 `MinesweeperLogic`（直接指定 `board`）、建立 `MinesweeperUI` 並呼叫 `start_replay(history=...)` |

#### 畫面切換機制

- 使用 `self.main_container`（`tk.Frame`）作為當前畫面容器。
- 切換畫面時先呼叫 `main_container.destroy()`，再重新建立新容器。
- 遊戲畫面由 `MinesweeperUI`（`tk.Frame`）直接嵌入主視窗，不使用 `main_container`。
- 遊戲結束後呼叫 `show_main_menu` 重建主選單容器。

#### 難度預設值

| 難度 | rows | cols | mines |
|------|------|------|-------|
| 簡單 | 8 | 8 | 10 |
| 普通 | 12 | 12 | 30 |
| 困難 | 16 | 16 | 60 |
| 自訂（預設） | 20 | 20 | 50 |

---

## 5. 遊戲邏輯規則

### 勝利條件

```
翻開格子數 == 總格子數 − 地雷數
```

即所有非地雷格子皆已翻開（旗標不影響勝敗判斷）。

### 地圖生成流程（生成後驗證架構）

`reset_board()` 在第一次點擊後執行，採「生成 → 計算 → 驗證 → 重試」迴圈：

```
1. 初始化 revealed（迴圈外，僅一次）
2. 隨機佈雷（跳過首點 3×3 禁區，使用 set 加速查找）
3. 計算各安全格周圍地雷數
4. _is_valid_board() 驗證：安全區連通 + 無 2×2 全雷塊
5. 通過 → 回傳 True；不通過 → 重試
6. 超過 MAX_GENERATION_ATTEMPTS=1000 次 → 回傳 False
```

`reset_board()` 回傳 `False` 時，`on_click()` 顯示錯誤訊息並呼叫 `exit_game()` 返回主選單。

### 第一格安全保護

地雷在**第一次點擊發生後**才生成，且以點擊座標為中心的 3×3 範圍內不會放置地雷，保證第一格點擊不踩雷。

### 安全區連通性（`_check_connectivity`）

以 BFS 從任意一個非地雷格出發，驗證所有非地雷格是否屬於同一八方向連通區。若不連通則地圖不合法，需重新生成。

### 禁止 2×2 全地雷區塊（`_has_2x2_mine_block`）

掃描所有 2×2 格子組合，若四格皆為地雷則地圖不合法，需重新生成。可有效提升盤面可讀性、降低猜測局面出現機率。

### 空白格自動展開

`expand()` 使用 **BFS queue**（取代原有遞迴 DFS），翻開值為 0 的格子時自動向 8 個方向展開，直到碰到數字格為止。BFS 可避免大型地圖超出 Python 預設遞迴深度限制（1000）。

`expand()` 是安全格插旗狀態的唯一清除點：若 BFS 到達一個尚未翻開但已插旗的安全格（探測器觸發或自動展開），`expand()` 負責將 `flag_count -= 1` 並清除旗標文字，確保剩餘地雷計數正確，且不會與 `reveal_radar_cell()` 發生重複計算。

### 點擊操作的封鎖規則

| 格子狀態 | 左鍵 | 右鍵 |
|----------|------|------|
| 已翻開（`revealed == True`） | 無反應 | 無反應 |
| 已插旗（按鈕文字 == 🚩） | 無反應 | 允許（取消插旗） |
| 探測器標記地雷（`(r,c) in radar_mines`） | 無反應 | 無反應 |
| 未翻開且首格未點擊（`first_click == True`） | 允許（翻開首格） | 警告後無反應 |
| 未翻開、首格已點擊、無旗無標記 | 允許 | 允許（插旗） |

### 剩餘地雷數量顯示

頂部資訊列中的**剩餘地雷**標籤即時顯示：

```
剩餘地雷 = mines_count - len(radar_mines) - flag_count
```

- `radar_mines`：探測器已揭示為地雷的格子數（每次 `reveal_radar_cell` 加入地雷格時增加）
- `flag_count`：目前插旗格數（每次 `on_right_click` 插旗 +1、取消旗 -1）
- 值可為負數（玩家插錯旗時）
- 呼叫 `update_mine_count_label()` 更新；觸發時機：插旗 / 取消旗、使用探測器後、回放中旗標重播時
- 回放開始時重置 `flag_count = 0`

### 雙擊左鍵自動翻開（快速開格）

對**已翻開的數字格**雙擊左鍵時執行以下流程：

1. 若格子未翻開、為空格（值 0）或地雷（值 -1），不處理。
2. 計算周圍 8 格中「已插旗（按鈕文字 == 🚩）或已被探測器標記（`(r,c) in radar_mines`）」的格子數 `marked`。
3. 若 `marked != val`（格子數字），不處理。
4. 條件滿足則自動翻開周圍所有「未插旗且未探測標記」的格子：
   - 若翻開的格子為地雷 → 引爆並結束遊戲。
   - 若翻開的格子為安全格 → 呼叫 `expand()`。
5. 翻開完畢後呼叫 `check_win()` 判斷是否勝利。
6. 此操作記入 `history`，格式為 `('auto_reveal', row, col)`，回放時重新執行 `on_double_click`。

### 金屬探測器不觸發遊戲結束

探測器揭示地雷時僅顯示視覺提示（黃底 💣），不觸發爆炸邏輯。揭示完畢後仍會呼叫 `check_win()` 判斷是否達成勝利條件。

### 回放模式限制

回放期間（`is_replaying == True`）：
- 玩家點擊與右鍵操作無效。
- 翻格與旗標由 `replay_step()` 主動驅動，或透過控制列手動操作。
- 回放開啟後直接進入**暫停狀態**，由玩家按「繼續」開始播放。
- 每步延遲由相鄰步驟時間戳差值決定（floor 1ms，無上限），播放速度受倍率影響。
- 點擊、爆炸、探測器等音效不重新播放。

### 回放控制列

`start_replay()` 在盤面下方建立一列控制 UI，包含以下五個元件：

| 元件 | 說明 |
|------|------|
| 暫停/繼續/返回（`btn_pause`） | 切換播放狀態；回放結束後顯示「返回」，點擊呼叫 `exit_game()` |
| 速度選單（`tk.OptionMenu`） | 切換倍率：0.5×、1×（預設）、2×、3×；切換時凍結目前時間基準，避免跳躍 |
| 上一步（`btn_prev`） | 暫停狀態下回退一步（呼叫 `_seek_to_index(max(-1, index-2))`） |
| 下一步（`btn_next`） | 暫停狀態下前進一步 |
| 時間軸滑塊（`replay_slider`） | 可拖移，範圍 0 至 `_replay_total_dur`，解析度 0.001 秒；拖移中不更新畫面，放開時 seek |

#### 時間插值（smooth tick）

每 200ms 執行 `_replay_smooth_tick()`，以以下公式計算當前遊戲時間並更新標籤與滑塊：

```
current_game_t = _replay_game_base + (monotonic() - _replay_wall_ref) × _replay_speed
```

暫停或回放結束時此 tick 自動停止（函式開頭檢查 `_replay_paused`）。

#### Seek 機制

- `_seek_to_index(n)`：同步將盤面重置並逐步執行 `history[0..n]`，完成後設 `_replay_index = n+1` 並更新滑塊與標籤。
- `_seek_to_time(t)`：對 `history` 做二分搜尋，找到最後一個時間戳 ≤ t 的步驟後呼叫 `_seek_to_index`。
- Slider 拖移期間以 `_replay_slider_busy` 旗標防止程式內 `slider.set()` 觸發 seek 回呼。

---

## 6. 資料結構

### `board[r][c]`（int）

```
-1  → 地雷
 0  → 安全且周圍無地雷
1–8 → 周圍有 N 顆地雷
```

### `revealed[r][c]`（bool）

```
True  → 已翻開（不可再點擊或插旗）
False → 尚未翻開
```

### `history`（list of tuple）

```python
[
    ('click',       3, 4,        1.234),   # t = 距首次點擊的秒數（3 位小數）
    ('flag',        1, 2,        3.567),
    ('radar',       5, 6, 'cross', 5.890),
    ('auto_reveal', 7, 8,        7.123),
]
```

`t` 為 `_elapsed()` 回傳值（float，相對於本局首次點擊的秒數，3 位小數）。儲存至 JSON 時 tuple 序列化為 list，`t` 仍為 float，讀取後以 `tuple()` 還原。

---

## 7. 事件流程

### 正常遊戲流程

```
MainMenu.show_main_menu()
  → show_difficulty_menu()
    → pre_game_setup(is_custom=False)
        → start_game()  ← 簡單 / 普通 / 困難直接啟動，不開對話框
    → pre_game_setup(is_custom=True)
        → GameSettingsDialog(show_player_fields=False)（模態）
          → start_game()
            → MinesweeperUI（嵌入主視窗）
              → 第一次 on_click() → reset_board() + 啟動計時器
              → 持續 on_click() / on_right_click() / use_radar()
              → 踩雷 or check_win() → end_game_flow()
                → _show_end_dialog()
                  → [儲存紀錄] _on_save_record() → fb.upload_replay() → exit_game()
                  → [上傳排名] _on_upload_rank() → fb.upload_score()
                  → [返回] exit_game()
                    → show_main_menu()

MainMenu.show_main_menu()
  → [回放記錄] ReplayListWindow
    → play_selected() → play_replay()
      → MinesweeperUI（嵌入主視窗）
        → start_replay(history=...) → replay_step() → exit_game()
          → show_main_menu()
```

### 計時器流程

```
第一次 on_click() 記錄 _start_ts = time.monotonic()，設 timer_running = True，呼叫 update_timer()
update_timer() 每 1000ms 以 int(monotonic() - _start_ts) 更新標籤（顯示整數秒）
遊戲結束（踩雷或勝利）：設 timer_running = False，呼叫 _elapsed() 取精確耗時存入 elapsed_time
elapsed_time 用於結束訊息、排行榜寫入、回放 meta，顯示格式為 {:.3f} 秒
```

---

## 8. 音效與資源管理

### 音效初始化

在 `MinesweeperUI.__init__` 中執行 `pygame.mixer.init()`，以 `try/except` 包覆所有檔案載入，失敗時將音效物件設為 `None`，遊戲仍可正常執行（靜音模式）。

### 播放邏輯

| 音效 | 觸發條件 | 回放中是否播放 |
|------|----------|----------------|
| `assets/click.mp3` | 左鍵一般翻格 | 否 |
| `assets/boom.mp3` | 踩到地雷 | 否 |
| `assets/radar.mp3` | 使用金屬探測器 | 否 |
| `assets/game_bgm.mp3` | 遊戲介面開啟時循環播放（`play(-1)`） | 是（已在播放） |
| `assets/menu_bgm.mp3` | 主選單開啟時循環播放（`play(-1)`） | — |

### 素材目錄

所有音效與圖片素材放於 `assets/` 資料夾（與 `MinesweeperGameUI.py` 同層）。程式碼以頂層常數定義路徑，同時相容開發環境與 PyInstaller 打包模式：

```python
import sys as _sys
_BASE = Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else Path(__file__).resolve().parent
ASSETS_DIR = _BASE / "assets"
del _sys, _BASE
```

各素材檔案皆以 `ASSETS_DIR / "filename"` 的 `Path` 物件傳入 pygame / PIL，不依賴終端機 cwd。

### 背景圖片

`assets/main_menu_bg.jpg` 在 `MainMenu.__init__` 中載入並縮放為 600×450，以 `ImageTk.PhotoImage` 儲存於 `self.bg_image`，避免被 Python 垃圾回收機制回收。失敗時改用純色背景（`#b0d8d2`）。

---

## 9. 打包與發布

### 工具

使用 **PyInstaller** 將專案打包為 Windows 執行檔。

```bash
pip install pyinstaller
```

### 路徑相容性處理

打包後程式在 `sys._MEIPASS` 暫存目錄下執行，需區分兩類路徑：

| 資料類型 | 開發模式路徑 | 打包模式路徑 |
|----------|-------------|-------------|
| `assets/`（唯讀資源） | `Path(__file__).parent / "assets"` | `Path(sys._MEIPASS) / "assets"` |
| `account.json`（使用者可寫） | `Path(__file__).parent / "account.json"` | `Path(sys.executable).parent / "account.json"` |

相關修改已分別實作於 `MinesweeperGameUI.py`（`ASSETS_DIR`）與 `account.py`（`ACCOUNT_FILE`）。

### 打包指令

在專案根目錄執行：

```bash
pyinstaller --onedir --windowed --name "踩地雷" --add-data "assets;assets" --icon "assets/icon.ico" MinesweeperGameUI.py
```

| 參數 | 說明 |
|------|------|
| `--onedir` | 輸出為資料夾（啟動快、較不易被防毒誤報） |
| `--windowed` | 不顯示 console 視窗（GUI 應用必加） |
| `--name "踩地雷"` | 執行檔與輸出資料夾名稱 |
| `--add-data "assets;assets"` | 將 `assets/` 捆綁至輸出目錄（Windows 用 `;`，macOS/Linux 用 `:`） |
| `--icon "assets/icon.ico"` | 執行檔圖示 |

輸出位於 `dist/踩地雷/`，結構如下：

```
dist/踩地雷/
├── 踩地雷.exe
├── assets/
├── _internal/          ← PyInstaller 相依檔（必須一同發布）
└── ...
```

### 壓縮發布

將整個 `dist/踩地雷/` 資料夾（含 `_internal/`）壓縮為 zip：

```bash
# PowerShell
Compress-Archive -Path "dist\踩地雷" -DestinationPath "踩地雷.zip"
```

> 每次重新打包前，建議先刪除舊的 `dist/` 與 `build/` 資料夾，避免快取殘留造成問題。

---

## 10. 已知限制與預留功能

| 項目 | 狀態 | 說明 |
|------|------|------|
| 帳號系統 | 已實作 | 玩家 ID 全域唯一，Recovery Key 跨裝置登入；帳號資訊存 Firebase |
| 回放記錄 | 已實作（雲端） | 遊戲結束後可上傳回放至 Firebase，需登入；回放清單為該玩家的雲端記錄 |
| 查看排名 | 已實作（雲端） | Firebase 排行榜，3 難度 × 3 挑戰類型，前 10 名，`LeaderboardWindow` 顯示（含 ID 顏色） |
| 離線遊玩 | 已實作 | 可在無網路狀態下遊玩，但遊戲結束後無法儲存或上傳 |
| Recovery Key 找回 | 未實作 | 遺失 Recovery Key 後無法取回帳號；唯一方式為重新註冊新 ID |
| 帳號顏色修改 | 未實作 | 目前顏色在註冊時確定，尚無線上修改功能 |
| 存檔 / 讀檔（遊戲中中斷） | 未實作 | 尚未支援在遊戲進行中途儲存狀態並於下次繼續 |
| 視窗自適應 | 部分 | 遊戲畫面以 `geometry("")` 重設為自動大小，超大地圖可能超出螢幕 |
| 計時器精度 | 毫秒級 | 遊戲中顯示整數秒；結束訊息、排行榜、回放清單顯示 3 位小數（`time.monotonic()` 計時） |
| 旗標計數 | 已實作 | 頂部「剩餘地雷」標籤即時顯示，可為負值 |
| 遞迴展開深度 | 已修正 | `expand()` 已改為 BFS queue，不受 Python 遞迴深度限制影響 |
