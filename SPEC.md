# 踩地雷遊戲 — 開發者規格文件

## 目錄

1. [專案概覽](#1-專案概覽)
2. [技術棧與相依套件](#2-技術棧與相依套件)
3. [架構設計](#3-架構設計)
4. [類別與函式規格](#4-類別與函式規格)
   - [center_window](#41-center_window)
   - [MinesweeperLogic](#42-minesweeperlogic)
   - [GameSettingsDialog](#43-gamesettingsdialog)
   - [MinesweeperUI](#44-minesweeperui)
   - [MainMenu](#45-mainmenu)
5. [遊戲邏輯規則](#5-遊戲邏輯規則)
6. [資料結構](#6-資料結構)
7. [事件流程](#7-事件流程)
8. [音效與資源管理](#8-音效與資源管理)
9. [已知限制與預留功能](#9-已知限制與預留功能)

---

## 1. 專案概覽

| 項目 | 內容 |
|------|------|
| 程式語言 | Python 3.11 |
| 主程式 | `MinesweeperGameUI.py` |
| UI 框架 | tkinter（標準函式庫） |
| 音效引擎 | pygame.mixer |
| 圖片處理 | Pillow（PIL） |
| 執行環境 | 桌面視窗應用程式（Windows 為主） |

---

## 2. 技術棧與相依套件

```
pillow    # 主選單背景圖片的載入與縮放
pygame    # 背景音樂與音效播放
tkinter   # 視窗、元件、對話框（Python 標準函式庫，無需安裝）
random    # 地雷隨機佈置（Python 標準函式庫）
```

---

## 3. 架構設計

### 分層架構

```
MainMenu（tk.Tk）
│  主視窗，負責主選單、難度選擇畫面的切換
│
├── GameSettingsDialog（tk.Toplevel）
│       開始遊戲前的模態設定視窗
│
└── MinesweeperUI（tk.Frame）
        遊戲主介面，內含：
        ├── MinesweeperLogic  ← 純邏輯層（無 UI 元件）
        └── 操作歷史 history（list）← 回放資料來源
```

### 關係說明

- `MainMenu` 是唯一的頂層視窗（`tk.Tk`），其餘介面皆嵌入其中或以子視窗呈現。
- `MinesweeperLogic` 不持有任何 tkinter 物件，可獨立測試。
- `MinesweeperUI` 持有 `MinesweeperLogic` 的參考，並在事件觸發時呼叫邏輯方法。
- 遊戲結束後，`MinesweeperUI` 呼叫 `on_close_callback`（即 `MainMenu.show_main_menu`）回到主選單。

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

**使用位置**：`GameSettingsDialog.__init__`、`MainMenu.__init__`、`MinesweeperUI.show_custom_end_dialog`、`MainMenu.start_game`

---

### 4.2 `MinesweeperLogic`

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

### 4.3 `GameSettingsDialog`

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
| `is_custom` | bool | False | 是否顯示自訂輸入欄位 |

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

### 4.4 `MinesweeperUI`

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
| `start_time` | int | 計時器秒數（每秒 +1） |
| `timer_running` | bool | 計時器是否運行中 |
| `is_replaying` | bool | 是否處於回放模式 |
| `radar_uses_left` | int | 金屬探測器剩餘次數 |
| `radar_type` | tk.StringVar | 目前選擇的探測模式（`"none"` / `"cross"` / `"area"`） |

#### 操作歷史格式（`history`）

```python
('click',       row, col)        # 左鍵點擊
('flag',        row, col)        # 右鍵旗標切換
('radar',       row, col, mode)  # 金屬探測器（mode: "cross" 或 "area"）
('auto_reveal', row, col)        # 雙擊左鍵自動翻開周圍格
```

#### 主要方法

| 方法 | 說明 |
|------|------|
| `create_widgets()` | 建立頂部資訊列（含剩餘地雷標籤）、工具面板（探測器）、盤面按鈕格 |
| `on_click(r, c, from_replay)` | 左鍵點擊處理；已插旗或探測器地雷格無反應，否則依模式分派至探測器或翻格 |
| `on_right_click(r, c, from_replay)` | 右鍵旗標切換；首格未翻則警告，探測器地雷格與已翻開的格子不可插旗；更新 `flag_count` 與剩餘地雷標籤 |
| `on_double_click(r, c, from_replay)` | 雙擊左鍵快速翻開；對已翻數字格，若周圍標記數等於格子數字則自動翻開剩餘未標記格 |
| `expand(r, c)` | BFS 翻開格子；值為 0 時自動展開相鄰 8 格 |
| `check_win()` | 判斷剩餘未翻格數是否等於地雷數 |
| `use_radar(r, c, mode)` | 執行探測器效果、更新剩餘次數與剩餘地雷標籤 |
| `reveal_radar_cell(nr, nc)` | 揭示單一格：地雷顯示黃底 💣 並加入 `radar_mines`，安全格呼叫 expand |
| `update_mine_count_label()` | 更新剩餘地雷標籤：`mines_count - len(radar_mines) - flag_count` |
| `update_timer()` | 每 1000ms 遞增 `start_time` 並更新標籤 |
| `end_game_flow(message)` | 停止計時，若有歷史則顯示自訂結束對話框 |
| `start_replay()` | 重置盤面視覺、`radar_mines`、`flag_count` 與 `revealed`，進入回放模式 |
| `replay_step(index)` | 逐步重播 `history[index]`（含 `auto_reveal` 動作），每步間隔 500ms |
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

### 4.5 `MainMenu`

```python
class MainMenu(tk.Tk)
```

**職責**：頂層視窗，管理主選單與難度選擇畫面的切換，以及遊戲的啟動。

#### 方法

| 方法 | 說明 |
|------|------|
| `show_main_menu()` | 顯示主選單（含背景圖、四個選單按鈕） |
| `show_difficulty_menu()` | 顯示難度選擇（簡單 / 普通 / 困難 / 自訂 + 返回） |
| `pre_game_setup(r, c, m, is_custom)` | 開啟 `GameSettingsDialog`，取得結果後啟動遊戲 |
| `start_game(r, c, m, p_id, p_color, radar_uses)` | 停止音樂、銷毀主選單容器、建立遊戲介面 |

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
- 翻格與旗標由 `replay_step()` 主動驅動。
- 點擊、爆炸、探測器等音效不重新播放。

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
    ('click', 3, 4),
    ('flag',  1, 2),
    ('radar', 5, 6, 'cross'),
    ...
]
```

---

## 7. 事件流程

### 正常遊戲流程

```
MainMenu.show_main_menu()
  → show_difficulty_menu()
    → pre_game_setup()
      → GameSettingsDialog（模態）
        → start_game()
          → MinesweeperUI（嵌入主視窗）
            → 第一次 on_click() → reset_board() + 啟動計時器
            → 持續 on_click() / on_right_click() / use_radar()
            → 踩雷 or check_win() → end_game_flow()
              → show_custom_end_dialog()
                → [回放] start_replay() → replay_step() → exit_game()
                → [離開] exit_game()
                  → show_main_menu()
```

### 計時器流程

```
第一次 on_click() 設 timer_running = True，呼叫 update_timer()
update_timer() 每 1000ms 遞增 start_time 並重新排程自身
遊戲結束（踩雷或勝利）設 timer_running = False 停止遞增
```

---

## 8. 音效與資源管理

### 音效初始化

在 `MinesweeperUI.__init__` 中執行 `pygame.mixer.init()`，以 `try/except` 包覆所有檔案載入，失敗時將音效物件設為 `None`，遊戲仍可正常執行（靜音模式）。

### 播放邏輯

| 音效 | 觸發條件 | 回放中是否播放 |
|------|----------|----------------|
| `click.mp3` | 左鍵一般翻格 | 否 |
| `boom.mp3` | 踩到地雷 | 否 |
| `radar.mp3` | 使用金屬探測器 | 否 |
| `game_bgm.mp3` | 遊戲介面開啟時循環播放（`play(-1)`） | 是（已在播放） |
| `menu_bgm.mp3` | 主選單開啟時循環播放（`play(-1)`） | — |

### 背景圖片

`main_menu_bg.jpg` 在 `MainMenu.__init__` 中載入並縮放為 600×450，以 `ImageTk.PhotoImage` 儲存於 `self.bg_image`，避免被 Python 垃圾回收機制回收。失敗時改用純色背景（`#b0d8d2`）。

---

## 9. 已知限制與預留功能

| 項目 | 狀態 | 說明 |
|------|------|------|
| 載入遊戲 | 預留 | 主選單按鈕僅顯示提示訊息，尚未實作存檔 / 讀檔 |
| 查看排名 | 預留 | 主選單按鈕僅顯示提示訊息，尚未實作排行榜 |
| 視窗自適應 | 部分 | 遊戲畫面以 `geometry("")` 重設為自動大小，超大地圖可能超出螢幕 |
| 計時器精度 | 整數秒 | 以 `after(1000)` 實作，不保證毫秒精度 |
| 旗標計數 | 已實作 | 頂部「剩餘地雷」標籤即時顯示，可為負值 |
| 遞迴展開深度 | 已修正 | `expand()` 已改為 BFS queue，不受 Python 遞迴深度限制影響 |
