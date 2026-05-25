from pathlib import Path
import tkinter as tk
from tkinter import messagebox, colorchooser, ttk
from PIL import Image, ImageTk
import random
import pygame
import json
from collections import deque
from datetime import datetime
import time
import firebase_client as fb
import account as acc

MAX_GENERATION_ATTEMPTS = 1000  # 地圖生成失敗保護：超過此次數則回報錯誤
DIFFICULTY_PRESETS = {(8, 8, 10): "easy", (12, 12, 30): "normal", (16, 16, 60): "hard"}

# 打包為執行檔時資源位於 sys._MEIPASS；開發環境則與原始碼同層
import sys as _sys
_BASE = Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else Path(__file__).resolve().parent
ASSETS_DIR = _BASE / "assets"
del _sys, _BASE


# 將視窗置中顯示於螢幕中央
def center_window(window):
    window.update_idletasks()  
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f'+{x}+{y}')

# ---遊戲邏輯層---
class MinesweeperLogic:
    def __init__(self, rows, cols, mines):
        self.rows = rows
        self.cols = cols
        self.mines_count = mines #地雷數量
        self.board = [] #格子內容，-1 代表地雷，0-8 代表周圍地雷數量
        self.revealed = [] # 表示哪些格子已被翻開，初始為 False
        self.first_click = True 

    # 生成後驗證架構：隨機佈雷→計算數字→驗證品質，不合法則重試，超過上限回傳 False
    def reset_board(self, start_r, start_c):
        self.revealed = [[False for _ in range(self.cols)] for _ in range(self.rows)]
        # 禁止在起始格周圍 3×3 範圍內放置地雷，保護首次點擊安全
        forbidden = {(start_r + dr, start_c + dc) for dr in [-1,0,1] for dc in [-1,0,1]}
        for _ in range(MAX_GENERATION_ATTEMPTS):
            self.board = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
            mines_placed = 0
            while mines_placed < self.mines_count:
                r, c = random.randint(0, self.rows-1), random.randint(0, self.cols-1)
                if (r, c) not in forbidden and self.board[r][c] != -1:
                    self.board[r][c] = -1
                    mines_placed += 1
            # 計算每個安全格周圍 8 格中的地雷數，填入 board
            for r in range(self.rows):
                for c in range(self.cols):
                    if self.board[r][c] == -1: continue
                    self.board[r][c] = sum(
                        1 for dr in [-1,0,1] for dc in [-1,0,1]
                        if 0 <= r+dr < self.rows and 0 <= c+dc < self.cols
                        and self.board[r+dr][c+dc] == -1
                    )
            if self._is_valid_board():
                return True
        return False  # 超過最大嘗試次數，無法生成合法地圖

    # 驗證盤面是否符合品質條件（安全區連通且無 2×2 全地雷區塊）
    def _is_valid_board(self):
        return self._check_connectivity() and not self._has_2x2_mine_block()

    # BFS 驗證所有非地雷格是否屬於同一連通區（八方向）
    def _check_connectivity(self):
        safe_cells = [(r, c) for r in range(self.rows) for c in range(self.cols) if self.board[r][c] != -1]
        if not safe_cells:
            return False
        visited = set()
        queue = deque([safe_cells[0]])
        visited.add(safe_cells[0])
        while queue:
            r, c = queue.popleft()
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < self.rows and 0 <= nc < self.cols and (nr,nc) not in visited and self.board[nr][nc] != -1:
                        visited.add((nr,nc))
                        queue.append((nr,nc))
        return len(visited) == len(safe_cells)

    # 檢查是否存在 2×2 全地雷區塊
    def _has_2x2_mine_block(self):
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                if (self.board[r][c] == self.board[r][c+1] ==
                        self.board[r+1][c] == self.board[r+1][c+1] == -1):
                    return True
        return False

    # 計算目前已經翻開的格子數量，判斷勝利條件
    def get_revealed_count(self):
        count = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.revealed[r][c]: count += 1
        return count

# --- 設定視窗 ---
class GameSettingsDialog(tk.Toplevel):
    def __init__(self, parent, default_r=8, default_c=8, default_m=8, is_custom=False,
                 default_id="Unknown", default_color="#000000", show_player_fields=True):
        super().__init__(parent)
        self.title("遊戲設定")
        self.is_custom = is_custom
        self.result = None
        self.player_color = default_color
        self._default_id = default_id
        self._show_player_fields = show_player_fields

        row = 0
        if show_player_fields:
            tk.Label(self, text="玩家 ID:").grid(row=row, column=0, padx=10, pady=5, sticky="e")
            self.id_entry = tk.Entry(self)
            self.id_entry.insert(0, default_id)
            self.id_entry.grid(row=row, column=1, padx=10, pady=5)
            row += 1

            tk.Label(self, text="ID 顏色:").grid(row=row, column=0, padx=10, pady=5, sticky="e")
            self.color_btn = tk.Button(self, text="選擇顏色", bg=self.player_color, fg="white", command=self.pick_color)
            self.color_btn.grid(row=row, column=1, padx=10, pady=5, sticky="we")
            row += 1

        # 預設探測器使用次數為 2
        self.radar_val = 2

        if is_custom:
            tk.Label(self, text="列數 (5-27):").grid(row=row, column=0, padx=10, pady=5, sticky="e")
            self.r_entry = tk.Entry(self)
            self.r_entry.insert(0, str(default_r))
            self.r_entry.grid(row=row, column=1, padx=10, pady=5)
            row += 1

            tk.Label(self, text="行數 (5-44):").grid(row=row, column=0, padx=10, pady=5, sticky="e")
            self.c_entry = tk.Entry(self)
            self.c_entry.insert(0, str(default_c))
            self.c_entry.grid(row=row, column=1, padx=10, pady=5)
            row += 1

            self.mine_range_label = tk.Label(self, text="地雷數量:")
            self.mine_range_label.grid(row=row, column=0, padx=10, pady=5, sticky="e")
            self.m_entry = tk.Entry(self)
            self.m_entry.insert(0, str(default_m))
            self.m_entry.grid(row=row, column=1, padx=10, pady=5)
            row += 1

            tk.Label(self, text="探測器次數(0~99):").grid(row=row, column=0, padx=10, pady=5, sticky="e")
            self.radar_entry = tk.Entry(self)
            self.radar_entry.insert(0, "2")
            self.radar_entry.grid(row=row, column=1, padx=10, pady=5)
            row += 1

            # 綁定列數與行數輸入框，即時更新地雷數量範圍標籤
            self.r_entry.bind("<KeyRelease>", self._update_mine_range_label)
            self.c_entry.bind("<KeyRelease>", self._update_mine_range_label)
            self._update_mine_range_label()
        else:
            self.r_val, self.c_val, self.m_val = default_r, default_c, default_m

        tk.Button(self, text="開始遊戲", command=self.on_confirm).grid(row=row, column=0, columnspan=2, pady=10)
        center_window(self)
        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)

    # 根據目前輸入的列數與行數，即時更新地雷數量可輸入範圍的顯示標籤
    def _update_mine_range_label(self, event=None):
        try:
            r = int(self.r_entry.get())
            c = int(self.c_entry.get())
            if 5 <= r <= 27 and 5 <= c <= 44:
                min_m = max(2, int(r * c * 0.1))
                max_m = int(r * c * 0.25)
                self.mine_range_label.config(text=f"地雷數量 ({min_m}-{max_m}):")
        except ValueError:
            pass

    @staticmethod
    def _darken_if_bright(hex_color, threshold=0.7):
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        lum = (0.299*r + 0.587*g + 0.114*b) / 255
        if lum > threshold:
            scale = threshold / lum
            r, g, b = int(r*scale), int(g*scale), int(b*scale)
        return f"#{r:02x}{g:02x}{b:02x}"

    # 開啟系統顏色選擇器；若亮度過高則自動等比調暗至可讀範圍
    def pick_color(self):
        color = colorchooser.askcolor(title="選擇玩家 ID 顏色")[1]
        if color:
            color = self._darken_if_bright(color)
            self.player_color = color
            self.color_btn.config(bg=color)

    # 驗證輸入值並將結果打包為 tuple 存入 self.result，通過後關閉對話框
    def on_confirm(self):
        if self._show_player_fields:
            p_id = self.id_entry.get().strip() or "Unknown"
        else:
            p_id = self._default_id
        if self.is_custom:
            try:
                r = int(self.r_entry.get())
                c = int(self.c_entry.get())
                m = int(self.m_entry.get())
                radar = int(self.radar_entry.get())
                if not (5 <= r <= 27): raise ValueError("列數超出範圍 (5-27)")
                if not (5 <= c <= 44): raise ValueError("行數超出範圍 (5-44)")
                min_m = max(2, int(r * c * 0.1))
                max_m = int(r * c * 0.25)
                if not (min_m <= m <= max_m): raise ValueError(f"地雷數量必須在 {min_m} 到 {max_m} 之間")
                if radar < 0: raise ValueError("探測次數不能為負數")
                if radar > 99: raise ValueError("探測次數不能超過99")
                self.result = (r, c, m, p_id, self.player_color, radar)
                self.destroy()
            except ValueError as e:
                messagebox.showerror("輸入錯誤", str(e))
        else:
            self.result = (self.r_val, self.c_val, self.m_val, p_id, self.player_color, self.radar_val)
            self.destroy()

# --- 遊戲介面層 ---
class MinesweeperUI(tk.Frame):
    def __init__(self, parent, logic, player_id, player_color, radar_uses, on_close_callback):
        super().__init__(parent)
        self.main_app = parent  # MainMenu 實例，用於存取帳號與登入視窗
        self.logic = logic
        self.player_id = player_id
        self.player_color = player_color
        self.on_close_callback = on_close_callback
        self.buttons = []
        self.elapsed_time = 0.0  # 遊戲結束時的精確耗時（秒，3 位小數）
        self._start_ts = 0.0     # monotonic 起始時間戳，首次點擊時設定
        self.timer_running = False
        self.is_replaying = False
        self.history = []
        self.radar_mines = set()  # 記錄探測器揭示出的地雷格座標，禁止後續點擊操作
        self.flag_count = 0       # 已插旗格子數，用於計算剩餘地雷顯示
        self.radar_used_count = 0 # 累計使用探測器次數，判定無道具榜資格
        self.flag_used_count = 0  # 曾插旗次數（取消後仍計），判定無道具無旗子榜資格

        self.radar_uses_left = radar_uses 
        self.radar_type = tk.StringVar(value="none") 
            
        # 初始化 pygame 音效模組並載入各音效檔，失敗時靜默略過（音效設為 None）
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(ASSETS_DIR / "game_bgm.mp3")
            pygame.mixer.music.set_volume(0.5)
            pygame.mixer.music.play(-1)
            self.click_sound = pygame.mixer.Sound(ASSETS_DIR / "click.mp3")
            self.boom_sound = pygame.mixer.Sound(ASSETS_DIR / "boom.mp3")
            self.radar_sound = pygame.mixer.Sound(ASSETS_DIR / "radar.mp3")
        except:
            self.click_sound = self.boom_sound = self.radar_sound = None
           
        self.create_widgets()
        self.pack(padx=20, pady=20)

    # 建立頂部資訊列（計時、玩家名稱、退出）、左側探測器面板與盤面按鈕格
    def create_widgets(self):
        top_frame = tk.Frame(self)
        top_frame.grid(row=0, column=0, columnspan=self.logic.cols + 1, sticky="ew", pady=5)
        
        self.timer_label = tk.Label(top_frame, text="時間: 0 秒", font=("微軟正黑體", 12, "bold"))
        self.timer_label.pack(side="left", padx=20)

        self.mine_count_label = tk.Label(top_frame, text=f"剩餘地雷: {self.logic.mines_count}", font=("微軟正黑體", 12, "bold"))
        self.mine_count_label.pack(side="left", padx=10)

        player_label = tk.Label(top_frame, text=f"玩家: {self.player_id}",
                                font=("微軟正黑體", 12, "bold"), fg=self.player_color)
        player_label.pack(side="left", padx=10)
        
        exit_btn = tk.Button(top_frame, text="退出遊戲", bg="#e74c3c", fg="white", 
                             command=self.exit_game, font=("微軟正黑體", 10, "bold"))
        exit_btn.pack(side="right", padx=20)
        
        tool_frame = tk.Frame(self, relief=tk.RIDGE, bd=2)
        tool_frame.grid(row=1, column=0, rowspan=self.logic.rows, padx=10, sticky="ns")
        
        tk.Label(tool_frame, text="📺金屬探測器", font=("微軟正黑體", 11, "bold")).pack(pady=(10, 0))
        self.radar_count_label = tk.Label(tool_frame, text=f"剩餘: {self.radar_uses_left} 次", font=("微軟正黑體", 10))
        self.radar_count_label.pack(pady=5)
        
        # 探測器模式選項：不使用 / 十字形（整行整列）/ 九宮格（3×3 範圍）
        tk.Radiobutton(tool_frame, text="🚫未使用", variable=self.radar_type, value="none").pack(anchor="w", padx=5)
        tk.Radiobutton(tool_frame, text="➕十字", variable=self.radar_type, value="cross").pack(anchor="w", padx=5)
        tk.Radiobutton(tool_frame, text="⬛九宮格", variable=self.radar_type, value="area").pack(anchor="w", padx=5)
        
        # 依列數與行數動態生成盤面按鈕，左鍵翻格、右鍵插旗
        for r in range(self.logic.rows):
            row_btns = []
            for c in range(self.logic.cols):
                btn = tk.Button(self, width=3, height=1, command=lambda r=r, c=c: self.on_click(r, c))
                btn.bind("<Button-3>", lambda e, r=r, c=c: self.on_right_click(r, c))
                btn.bind("<Double-Button-1>", lambda e, r=r, c=c: self.on_double_click(r, c))
                btn.grid(row=r + 1, column=c + 1)
                row_btns.append(btn)
            self.buttons.append(row_btns)

    # 左鍵點擊事件：已插旗或探測器標記地雷的格子無反應，否則依模式分派至探測器或翻格邏輯
    def on_click(self, r, c, from_replay=False):
        if self.is_replaying and not from_replay: return
        if not from_replay:
            if self.buttons[r][c].cget("text") == "🚩": return
            if (r, c) in self.radar_mines: return
        if not from_replay:
            t = 0.0 if self.logic.first_click else self._elapsed()
            self.history.append(('click', r, c, t))

        current_mode = self.radar_type.get()
        if current_mode != "none":
            if self.logic.first_click:
                messagebox.showwarning("警告", "請先點開第一格後再使用金屬探測器！")
                self.radar_type.set("none")
                return
            if self.radar_uses_left > 0:
                self.use_radar(r, c, current_mode)
                return
            else:
                messagebox.showwarning("警告", "道具使用次數已用盡")
                self.radar_type.set("none")
                return

        if self.click_sound and not self.is_replaying: self.click_sound.play()
        # 第一次點擊時初始化地雷盤面並啟動計時器
        if self.logic.first_click:
            if not self.logic.reset_board(r, c):
                messagebox.showerror("地圖生成失敗", "無法在目前設定下生成合法地圖，請調整地雷數量或地圖大小後重試。")
                self.exit_game()
                return
            self.logic.first_click = False
            self._start_ts = time.monotonic()
            self.timer_running = True
            self.update_timer()
            
        if self.logic.board[r][c] == -1:
            if self.boom_sound and not self.is_replaying: self.boom_sound.play()
            self.timer_running = False
            self.buttons[r][c].config(text="💣", bg="red")
            if not from_replay:
                self.elapsed_time = self._elapsed()
                self.end_game_flow(f"玩家: {self.player_id}\n踩到地雷了！耗時: {self.elapsed_time:.3f} 秒")
        else:
            self.expand(r, c)
            if not from_replay: self.check_win()

    # 右鍵點擊事件：未翻第一格則警告，探測器地雷格與已翻開的格子不可插旗
    def on_right_click(self, r, c, from_replay=False):
        if self.is_replaying and not from_replay: return
        if not from_replay:
            if self.logic.first_click:  # 盤面尚未初始化，revealed 為空列表，須在此提前攔截
                messagebox.showwarning("警告", "請先點開第一格後再插旗！")
                return
        if self.logic.revealed[r][c]: return  # 此時 first_click 必為 False，revealed 已初始化，可安全存取
        if not from_replay:
            if (r, c) in self.radar_mines: return
            self.history.append(('flag', r, c, self._elapsed()))
        curr = self.buttons[r][c].cget("text")
        self.buttons[r][c].config(text="🚩" if curr == "" else "", fg="red")
        self.flag_count += (1 if curr == "" else -1)
        if not from_replay and curr == "":
            self.flag_used_count += 1
        self.update_mine_count_label()

    # 雙擊左鍵快速翻開：若周圍已標記數等於格子數字，自動翻開剩餘未標記格（踩雷仍會引爆）
    def on_double_click(self, r, c, from_replay=False):
        if self.is_replaying and not from_replay: return
        if self.logic.first_click: return
        if not self.logic.revealed[r][c]: return
        val = self.logic.board[r][c]
        if val <= 0: return
        marked = sum(
            1 for dr in [-1, 0, 1] for dc in [-1, 0, 1]
            if not (dr == 0 and dc == 0)
            and 0 <= r+dr < self.logic.rows and 0 <= c+dc < self.logic.cols
            and (self.buttons[r+dr][c+dc].cget("text") == "🚩" or (r+dr, c+dc) in self.radar_mines)
        )
        if marked != val: return
        if not from_replay:
            self.history.append(('auto_reveal', r, c, self._elapsed()))
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r+dr, c+dc
                if not (0 <= nr < self.logic.rows and 0 <= nc < self.logic.cols): continue
                if self.logic.revealed[nr][nc]: continue
                if self.buttons[nr][nc].cget("text") == "🚩": continue
                if (nr, nc) in self.radar_mines: continue
                if self.logic.board[nr][nc] == -1:
                    if self.boom_sound and not self.is_replaying: self.boom_sound.play()
                    self.timer_running = False
                    self.buttons[nr][nc].config(text="💣", bg="red")
                    if not from_replay:
                        self.elapsed_time = self._elapsed()
                        self.end_game_flow(f"玩家: {self.player_id}\n踩到地雷了！耗時: {self.elapsed_time:.3f} 秒")
                    return
                else:
                    self.expand(nr, nc)
        if not from_replay: self.check_win()

    # 遊戲結束流程：停止計時並顯示結束對話框
    def end_game_flow(self, message, result="lose"):
        self.timer_running = False
        if self.history:
            self._show_end_dialog(message, result)
        else:
            messagebox.showinfo("遊戲結束", message)
            self.exit_game()

    # 遊戲結束對話框：三個按鈕（儲存紀錄 / 上傳排名 / 返回主選單）
    def _show_end_dialog(self, message, result):
        difficulty = DIFFICULTY_PRESETS.get(
            (self.logic.rows, self.logic.cols, self.logic.mines_count))
        can_rank = (result == "win" and difficulty is not None)

        dialog = tk.Toplevel(self)
        dialog.title("遊戲結束")
        dialog.resizable(False, False)
        center_window(dialog)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text=message, font=("微軟正黑體", 11), pady=16).pack()

        if not can_rank:
            reason = "自訂模式不入榜" if result == "win" else "遊戲失敗不入榜"
            tk.Label(dialog, text=f"（{reason}）",
                     font=("微軟正黑體", 9), fg="gray").pack(pady=(0, 4))

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=12)

        self._end_btn_save = tk.Button(btn_frame, text="儲存遊戲紀錄", width=13,
                  command=lambda: self._on_save_record(result, dialog))
        self._end_btn_save.pack(side="left", padx=6)

        self._end_btn_rank = tk.Button(btn_frame, text="上傳排名", width=10,
                  state=tk.NORMAL if can_rank else tk.DISABLED,
                  command=lambda: self._on_upload_rank(difficulty, dialog))
        self._end_btn_rank.pack(side="left", padx=6)

        tk.Button(btn_frame, text="返回主選單", width=10,
                  command=lambda: [dialog.destroy(), self.exit_game()]
                  ).pack(side="left", padx=6)

    def _on_save_record(self, result, dialog):
        if self.main_app.account is None:
            dialog.grab_release()
            def _after():
                if dialog.winfo_exists():
                    dialog.lift()
                    dialog.grab_set()
                    self._do_save_record(result, dialog)
            self.main_app.show_login_window(callback=_after)
            return
        self._do_save_record(result, dialog)

    def _do_save_record(self, result, dialog):
        pid = self.main_app.account["player_id"]
        data = self._build_replay_data(result)
        key = fb.upload_replay(pid, data)
        if key:
            if hasattr(self, '_end_btn_save') and self._end_btn_save.winfo_exists():
                self._end_btn_save.config(state=tk.DISABLED)
            messagebox.showinfo("已儲存", "遊戲紀錄已上傳至雲端。", parent=dialog)
        else:
            messagebox.showerror("上傳失敗", "無法連線至伺服器，請確認網路連線。", parent=dialog)

    def _on_upload_rank(self, difficulty, dialog):
        if self.main_app.account is None:
            dialog.grab_release()
            def _after():
                if dialog.winfo_exists():
                    dialog.lift()
                    dialog.grab_set()
                    self._do_upload_rank(difficulty, dialog)
            self.main_app.show_login_window(callback=_after)
            return
        self._do_upload_rank(difficulty, dialog)

    def _do_upload_rank(self, difficulty, dialog):
        pid   = self.main_app.account["player_id"]
        color = self.main_app.account.get("color", "#000000")
        # 排行榜直接嵌入回放資料，與 records/ 下的個人紀錄完全獨立
        replay = self._build_replay_data("win")
        ok = fb.upload_score(difficulty, pid, color, self.elapsed_time, "unlimited", replay)
        if self.radar_used_count == 0:
            fb.upload_score(difficulty, pid, color, self.elapsed_time, "no_item", replay)
            if self.flag_used_count == 0:
                fb.upload_score(difficulty, pid, color, self.elapsed_time, "no_item_no_flag", replay)
        if ok:
            if hasattr(self, '_end_btn_rank') and self._end_btn_rank.winfo_exists():
                self._end_btn_rank.config(state=tk.DISABLED)
            messagebox.showinfo("已上傳", "排名已上傳至雲端排行榜。", parent=dialog)
        else:
            messagebox.showerror("上傳失敗", "無法連線至伺服器，請確認網路連線。", parent=dialog)

    # 打包本局所有資料為 Replay dict
    def _build_replay_data(self, result):
        difficulty = DIFFICULTY_PRESETS.get(
            (self.logic.rows, self.logic.cols, self.logic.mines_count), "custom")
        return {
            "version": 1,
            "meta": {
                "player_id": self.player_id,
                "player_color": self.player_color,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "time_sec": self.elapsed_time,
                "result": result,
                "difficulty": difficulty
            },
            "settings": {
                "rows": self.logic.rows,
                "cols": self.logic.cols,
                "mines": self.logic.mines_count,
                "radar_uses": self.radar_uses_left + self.radar_used_count
            },
            "board": self.logic.board,
            "history": [list(h) for h in self.history]
        }

    # 重置盤面視覺狀態並進入回放模式；傳入 history 時覆蓋目前紀錄（供檔案回放使用）
    def start_replay(self, history=None):
        if history is not None:
            self.history = history
        self.is_replaying = True
        self.timer_running = False
        self.radar_mines = set()
        self.flag_count = 0
        self.logic.revealed = [[False] * self.logic.cols for _ in range(self.logic.rows)]
        for r in range(self.logic.rows):
            for c in range(self.logic.cols):
                self.buttons[r][c].config(text="", bg="SystemButtonFace", state=tk.NORMAL, relief=tk.RAISED)
        self.elapsed_time = 0.0
        self._start_ts    = 0.0

        self._replay_index        = 0
        self._replay_paused       = True
        self._replay_speed        = 1.0
        self._replay_game_base    = 0.0
        self._replay_wall_ref     = time.monotonic()
        self._replay_total_dur    = self.history[-1][-1] if self.history else 1.0
        self._replay_slider_busy  = False
        self._replay_after_id     = None
        self._slider_pending_value = None

        self.timer_label.config(text="時間: 0 秒")

        replay_bar = tk.Frame(self)
        replay_bar.grid(row=self.logic.rows + 1, column=0,
                        columnspan=self.logic.cols + 1, sticky="ew", pady=(4, 0))
        replay_bar.columnconfigure(4, weight=1)

        self.btn_pause = tk.Button(replay_bar, text="繼續", width=6,
                                   command=self._toggle_replay_pause)
        self.btn_pause.grid(row=0, column=0, padx=(4, 2))

        self._speed_var = tk.StringVar(value="1×")
        self._speed_var.trace("w", self._on_speed_change)
        speed_menu = tk.OptionMenu(replay_bar, self._speed_var, "0.5×", "1×", "2×", "3×")
        speed_menu.config(width=4)
        speed_menu.grid(row=0, column=1, padx=2)

        self.btn_prev = tk.Button(replay_bar, text="上一步", command=self._replay_prev)
        self.btn_prev.grid(row=0, column=2, padx=2)

        self.btn_next = tk.Button(replay_bar, text="下一步", command=self._replay_next)
        self.btn_next.grid(row=0, column=3, padx=2)

        self.replay_slider = tk.Scale(
            replay_bar, from_=0, to=self._replay_total_dur,
            resolution=0.001, orient=tk.HORIZONTAL, showvalue=0,
            command=self._on_slider_cmd
        )
        self.replay_slider.grid(row=0, column=4, sticky="ew", padx=(2, 4))
        self.replay_slider.bind("<ButtonPress-1>",   self._on_slider_press)
        self.replay_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        self._update_replay_buttons()

    # 執行單一 history 紀錄（不更新 index 或時間戳），供 replay_step / next / seek 共用
    def _execute_replay_record(self, record):
        action = record[0]
        if action == 'click':
            r, c = record[1], record[2]
            if self.logic.board[r][c] == -1:
                self.buttons[r][c].config(text="💣", bg="red")
            else:
                self.expand(r, c)
        elif action == 'flag':
            r, c = record[1], record[2]
            curr = self.buttons[r][c].cget("text")
            if not self.logic.revealed[r][c]:
                self.buttons[r][c].config(text="🚩" if curr == "" else "", fg="red")
                self.flag_count += (1 if curr == "" else -1)
                self.update_mine_count_label()
        elif action == 'auto_reveal':
            r, c = record[1], record[2]
            self.on_double_click(r, c, from_replay=True)
        elif action == 'radar':
            r, c, mode = record[1], record[2], record[3]
            self.use_radar(r, c, mode)

    # 每 200ms 根據 wall clock × 速度插值更新 timer_label 與滑塊，暫停或回放結束時自動停止
    def _replay_smooth_tick(self):
        if not self.winfo_exists(): return
        if not self.is_replaying or self._replay_paused: return
        current = self._replay_game_base + (time.monotonic() - self._replay_wall_ref) * self._replay_speed
        current = min(current, self._replay_total_dur)
        self.timer_label.config(text=f"時間: {int(current)} 秒")
        self._replay_slider_busy = True
        self.replay_slider.set(current)
        self._replay_slider_busy = False
        self.after(200, self._replay_smooth_tick)

    # 逐步重播：以 _replay_index 驅動，依時間戳間距排程下一步
    def replay_step(self):
        if not self.winfo_exists(): return
        if self._replay_paused: return
        if self._replay_index >= len(self.history):
            self.is_replaying  = False
            self._replay_paused = True
            self._update_replay_buttons()
            return
        record = self.history[self._replay_index]
        self._execute_replay_record(record)
        game_t                 = record[-1]
        self._replay_game_base = game_t
        self._replay_wall_ref  = time.monotonic()
        self._replay_index    += 1
        self.timer_label.config(text=f"時間: {int(game_t)} 秒")
        self._replay_slider_busy = True
        self.replay_slider.set(game_t)
        self._replay_slider_busy = False
        if self._replay_index < len(self.history):
            next_t   = self.history[self._replay_index][-1]
            delta_ms = max(1, int((next_t - game_t) * 1000 / self._replay_speed))
        else:
            delta_ms = 1
        self._replay_after_id = self.after(delta_ms, self.replay_step)

    # 同步 seek 至「最後執行步驟 = n」的盤面狀態，維持暫停（n=-1 代表回到初始狀態）
    def _seek_to_index(self, n):
        self.is_replaying = True
        self.radar_mines  = set()
        self.flag_count   = 0
        self.logic.revealed = [[False] * self.logic.cols for _ in range(self.logic.rows)]
        for r in range(self.logic.rows):
            for c in range(self.logic.cols):
                self.buttons[r][c].config(text="", bg="SystemButtonFace", state=tk.NORMAL, relief=tk.RAISED)
        if n >= 0:
            for i in range(n + 1):
                self._execute_replay_record(self.history[i])
        self._replay_index     = n + 1
        game_t                 = self.history[n][-1] if n >= 0 else 0.0
        self._replay_game_base = game_t
        self._replay_wall_ref  = time.monotonic()
        self.update_mine_count_label()
        self.timer_label.config(text=f"時間: {int(game_t)} 秒")
        self._replay_slider_busy = True
        self.replay_slider.set(game_t)
        self._replay_slider_busy = False
        self._update_replay_buttons()

    # 以時間（秒）為目標，二分搜尋最近步驟後 seek
    def _seek_to_time(self, target_time):
        if not self.history or target_time < self.history[0][-1]:
            self._seek_to_index(-1)
            return
        lo, hi = 0, len(self.history) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.history[mid][-1] <= target_time:
                lo = mid
            else:
                hi = mid - 1
        self._seek_to_index(lo)

    # 根據目前狀態更新四個控制元件的文字與啟用狀態
    def _update_replay_buttons(self):
        ended = self._replay_index >= len(self.history)
        if ended:
            self.btn_pause.config(text="返回")
        elif self._replay_paused:
            self.btn_pause.config(text="繼續")
        else:
            self.btn_pause.config(text="暫停")
        self.btn_prev.config(
            state=tk.NORMAL if self._replay_paused and self._replay_index > 0 else tk.DISABLED)
        self.btn_next.config(
            state=tk.NORMAL if self._replay_paused and not ended else tk.DISABLED)

    def _toggle_replay_pause(self):
        if self._replay_index >= len(self.history):
            self.exit_game()
            return
        if self._replay_paused:
            self._replay_paused   = False
            self._replay_wall_ref = time.monotonic()
            self._replay_smooth_tick()
            self.replay_step()
        else:
            if self._replay_after_id is not None:
                self.after_cancel(self._replay_after_id)
                self._replay_after_id = None
            current = self._replay_game_base + (time.monotonic() - self._replay_wall_ref) * self._replay_speed
            self._replay_game_base = min(current, self._replay_total_dur)
            self._replay_paused = True
        self._update_replay_buttons()

    def _on_speed_change(self, *_):
        speed_map = {"0.5×": 0.5, "1×": 1.0, "2×": 2.0, "3×": 3.0}
        new_speed = speed_map.get(self._speed_var.get(), 1.0)
        if not self._replay_paused:
            current = self._replay_game_base + (time.monotonic() - self._replay_wall_ref) * self._replay_speed
            self._replay_game_base = min(current, self._replay_total_dur)
            self._replay_wall_ref  = time.monotonic()
        self._replay_speed = new_speed

    def _replay_prev(self):
        if not self._replay_paused: return
        self._seek_to_index(max(-1, self._replay_index - 2))

    def _replay_next(self):
        if not self._replay_paused: return
        if self._replay_index >= len(self.history): return
        record = self.history[self._replay_index]
        self._execute_replay_record(record)
        game_t                 = record[-1]
        self._replay_game_base = game_t
        self._replay_wall_ref  = time.monotonic()
        self._replay_index    += 1
        self.update_mine_count_label()
        self.timer_label.config(text=f"時間: {int(game_t)} 秒")
        self._replay_slider_busy = True
        self.replay_slider.set(game_t)
        self._replay_slider_busy = False
        self._update_replay_buttons()

    def _on_slider_press(self, event):
        self._slider_pending_value = None
        if not self._replay_paused:
            if self._replay_after_id is not None:
                self.after_cancel(self._replay_after_id)
                self._replay_after_id = None
            current = self._replay_game_base + (time.monotonic() - self._replay_wall_ref) * self._replay_speed
            self._replay_game_base = min(current, self._replay_total_dur)
            self._replay_paused = True
            self._update_replay_buttons()

    def _on_slider_release(self, event):
        if self._replay_slider_busy: return
        val = self._slider_pending_value
        self._slider_pending_value = None
        if val is not None:
            self._seek_to_time(val)

    def _on_slider_cmd(self, value):
        # 追蹤使用者主動改變的滑塊值（程式內部 set() 時 _replay_slider_busy=True 會跳過）
        if not self._replay_slider_busy:
            self._slider_pending_value = float(value)

    # BFS 翻開格子（取代遞迴 DFS），避免大型地圖超出 Python 遞迴深度限制
    def expand(self, r, c):
        colors = {1: "blue", 2: "green", 3: "red", 4: "darkblue", 5: "darkred", 6: "cyan", 7: "black", 8: "grey"}
        queue = deque([(r, c)])
        while queue:
            r, c = queue.popleft()
            if not (0 <= r < self.logic.rows and 0 <= c < self.logic.cols): continue
            if self.logic.revealed[r][c]: continue
            if self.buttons[r][c].cget("text") == "🚩":
                self.flag_count -= 1
            self.logic.revealed[r][c] = True
            val = self.logic.board[r][c]
            self.buttons[r][c].config(text=str(val) if val > 0 else "", relief=tk.SUNKEN, bg="#d1d1d1",
                                      state=tk.DISABLED, disabledforeground=colors.get(val, "black"))
            if val == 0:
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if not (dr == 0 and dc == 0):
                            queue.append((r + dr, c + dc))

    # 勝利判定：剩餘未翻格數等於地雷數時觸發勝利流程
    def check_win(self):
        if (self.logic.rows * self.logic.cols) - self.logic.get_revealed_count() == self.logic.mines_count:
            self.timer_running = False
            self.elapsed_time = self._elapsed()
            self.end_game_flow(f"勝利！恭喜 {self.player_id}！\n總耗時: {self.elapsed_time:.3f} 秒", result="win")

    # 執行金屬探測器效果，依模式揭示十字或九宮格範圍內的所有格子
    def use_radar(self, r, c, mode):
        if self.radar_sound and not self.is_replaying: self.radar_sound.play()
        if not self.is_replaying:
            self.history.append(('radar', r, c, mode, self._elapsed()))
            self.radar_uses_left -= 1
            self.radar_used_count += 1
        if mode == "area":
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]: self.reveal_radar_cell(r + dr, c + dc)
        elif mode == "cross":
            for i in range(self.logic.cols): self.reveal_radar_cell(r, i)
            for i in range(self.logic.rows): self.reveal_radar_cell(i, c)
        self.radar_type.set("none")
        self.radar_count_label.config(text=f"剩餘: {self.radar_uses_left}")
        self.update_mine_count_label()

        if not self.is_replaying:
            self.check_win()

    # 揭示單一格子：地雷顯示黃底圖示（地雷格旗標在此處理），安全格交由 expand 處理旗標
    def reveal_radar_cell(self, nr, nc):
        if 0 <= nr < self.logic.rows and 0 <= nc < self.logic.cols:
            if self.logic.board[nr][nc] == -1:
                if self.buttons[nr][nc].cget("text") == "🚩":
                    self.flag_count -= 1
                self.buttons[nr][nc].config(text="💣", fg="black", bg="#f1c40f")
                self.radar_mines.add((nr, nc))
            else:
                self.expand(nr, nc)
                

    # 更新剩餘地雷數量標籤：地雷總數 - 已被探測器揭示的地雷數 - 已插旗格數
    def update_mine_count_label(self):
        remaining = self.logic.mines_count - len(self.radar_mines) - self.flag_count
        self.mine_count_label.config(text=f"剩餘地雷: {remaining}")

    def _elapsed(self) -> float:
        return round(time.monotonic() - self._start_ts, 3)

    # 每秒更新計時器顯示標籤（遊戲進行中顯示整數秒），timer_running 為 False 時自動停止
    def update_timer(self):
        if self.timer_running:
            self.timer_label.config(text=f"時間: {int(time.monotonic() - self._start_ts)} 秒")
            self.after(1000, self.update_timer)

    # 停止背景音樂、銷毀遊戲介面並執行返回主選單的回呼函式
    def exit_game(self):
        pygame.mixer.music.stop()
        self.destroy()
        self.on_close_callback()

# --- 排行榜視窗 ---
class LeaderboardWindow(tk.Toplevel):
    _DIFF = {"簡單": "easy", "普通": "normal", "困難": "hard"}
    _CAT  = {"無限制": "unlimited", "無道具": "no_item", "無道具無旗子": "no_item_no_flag"}

    def __init__(self, parent):
        super().__init__(parent)
        self.title("排行榜")
        self.resizable(False, False)
        self._parent  = parent
        self._records = []

        top_frame = tk.Frame(self, pady=8)
        top_frame.pack()

        tk.Label(top_frame, text="難度:", font=("微軟正黑體", 11)).pack(side="left")
        self.diff_var = tk.StringVar(value="簡單")
        tk.OptionMenu(top_frame, self.diff_var, "簡單", "普通", "困難",
                      command=lambda _: self.refresh()).pack(side="left", padx=4)

        tk.Label(top_frame, text="挑戰類型:", font=("微軟正黑體", 11)).pack(side="left", padx=(12, 0))
        self.cat_var = tk.StringVar(value="無限制")
        tk.OptionMenu(top_frame, self.cat_var, "無限制", "無道具", "無道具無旗子",
                      command=lambda _: self.refresh()).pack(side="left", padx=4)

        self.tree = ttk.Treeview(self, columns=("rank", "player", "time", "date"),
                                 show="headings", height=10, selectmode="browse")
        for col, label, w in [("rank", "排名", 50), ("player", "玩家 ID", 120),
                               ("time", "時間", 80), ("date", "日期", 120)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=w, anchor="center")
        self.tree.pack(padx=12, pady=(0, 4))

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(0, 12))
        tk.Button(btn_frame, text="回放", width=10, command=self.play_selected).pack(side="left", padx=6)
        tk.Button(btn_frame, text="重新整理", width=10, command=self.refresh).pack(side="left", padx=6)

        self.refresh()
        center_window(self)
        self.transient(parent)

    def refresh(self):
        diff = self._DIFF[self.diff_var.get()]
        cat  = self._CAT[self.cat_var.get()]
        records = fb.get_leaderboard(diff, cat)
        self.tree.delete(*self.tree.get_children())
        if records is None:
            messagebox.showerror("錯誤", "無法連線至伺服器，請確認網路連線。", parent=self)
            self._records = []
            return
        self._records = records
        for i, rec in enumerate(records, 1):
            color = rec.get("player_color", "#000000")
            tag = f"c{color[1:]}"
            self.tree.tag_configure(tag, foreground=color)
            self.tree.insert("", "end", values=(
                i, rec["player_id"], f"{rec['time_sec']:.3f} 秒", rec.get("date", "")[:10]
            ), tags=(tag,))

    def play_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選擇一筆排名記錄。", parent=self)
            return
        idx  = self.tree.index(sel[0])
        rec  = self._records[idx]
        data = rec.get("replay")
        if not data or not all(k in data for k in ("version", "board", "history")):
            messagebox.showinfo("提示", "此筆排名沒有關聯的回放資料。", parent=self)
            return
        self.destroy()
        self._parent.play_replay(data)

# --- 回放清單視窗 ---
class ReplayListWindow(tk.Toplevel):
    _DIFF_LABEL   = {"easy": "簡單", "normal": "普通", "hard": "困難", "custom": "自訂"}
    _RESULT_LABEL = {"win": "勝利", "lose": "失敗"}

    def __init__(self, parent, account: dict):
        super().__init__(parent)
        self.title("回放記錄")
        self.resizable(False, False)
        self._parent  = parent
        self._account = account

        self.tree = ttk.Treeview(self,
            columns=("player", "diff", "result", "time", "date"),
            show="headings", height=12, selectmode="browse")
        for col, label, w in [("player", "玩家", 120), ("diff", "難度", 60),
                               ("result", "結果", 60), ("time", "時間", 70), ("date", "日期", 110)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=w, anchor="center")
        self.tree.pack(padx=12, pady=(12, 4))

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(4, 12))
        tk.Button(btn_frame, text="開始回放", width=10, command=self.play_selected).pack(side="left", padx=6)
        tk.Button(btn_frame, text="刪除",     width=8,  command=self.delete_selected).pack(side="left", padx=6)
        tk.Button(btn_frame, text="重新整理", width=10, command=self.refresh).pack(side="left", padx=6)

        self._records = []
        self.refresh()
        center_window(self)
        self.transient(parent)

    def refresh(self):
        pid = self._account["player_id"]
        records = fb.get_replay_list(pid)
        self.tree.delete(*self.tree.get_children())
        if records is None:
            messagebox.showerror("錯誤", "無法連線至伺服器，請確認網路連線。", parent=self)
            self._records = []
            return
        self._records = records
        for rec in records:
            color = rec["player_color"]
            tag = f"c{color[1:]}"
            self.tree.tag_configure(tag, foreground=color)
            self.tree.insert("", "end", values=(
                rec["player_id"],
                self._DIFF_LABEL.get(rec["difficulty"], rec["difficulty"]),
                self._RESULT_LABEL.get(rec["result"], rec["result"]),
                f"{rec['time_sec']:.3f} 秒",
                rec["date"]
            ), tags=(tag,))

    def play_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選擇一筆回放記錄。", parent=self)
            return
        idx = self.tree.index(sel[0])
        data = self._records[idx]["full_data"]
        if not all(k in data for k in ("version", "board", "history")):
            messagebox.showerror("載入失敗", "無效的回放資料格式。", parent=self)
            return
        self.destroy()
        self._parent.play_replay(data)

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        rec = self._records[idx]
        if messagebox.askyesno("確認刪除", "確定要刪除此回放記錄？", parent=self):
            ok = fb.delete_replay(self._account["player_id"], rec["record_id"])
            if ok:
                self.refresh()
            else:
                messagebox.showerror("刪除失敗", "無法連線至伺服器。", parent=self)

# --- 登入視窗 ---
class LoginWindow(tk.Toplevel):
    def __init__(self, main_app, on_success=None):
        super().__init__(main_app)
        self._main_app  = main_app
        self._on_success = on_success
        self.title("玩家登入")
        self.resizable(False, False)

        tk.Label(self, text="玩家 ID:", font=("微軟正黑體", 11)).grid(
            row=0, column=0, padx=16, pady=10, sticky="e")
        self.id_entry = tk.Entry(self, width=22)
        self.id_entry.grid(row=0, column=1, padx=12, pady=10)

        tk.Label(self, text="Recovery Key:", font=("微軟正黑體", 11)).grid(
            row=1, column=0, padx=16, pady=6, sticky="e")
        self.key_entry = tk.Entry(self, width=22)
        self.key_entry.grid(row=1, column=1, padx=12, pady=6)

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="登入", width=9, command=self._on_login).pack(side="left", padx=8)
        tk.Button(btn_frame, text="取消", width=9, command=self.destroy).pack(side="left", padx=8)

        link_frame = tk.Frame(self)
        link_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        tk.Label(link_frame, text="沒有帳號？", font=("微軟正黑體", 10)).pack(side="left")
        tk.Button(link_frame, text="點此註冊", font=("微軟正黑體", 10),
                  relief="flat", fg="blue", cursor="hand2",
                  command=self._open_register).pack(side="left")

        center_window(self)
        self.transient(main_app)
        self.grab_set()

    def _on_login(self):
        pid = self.id_entry.get().strip()
        key = self.key_entry.get().strip()
        if not pid or not key:
            messagebox.showwarning("提示", "請輸入玩家 ID 與 Recovery Key", parent=self)
            return
        key_hash = acc.hash_key(key)
        ok, result = fb.verify_login(pid, key_hash)
        if ok:
            color   = result
            account = acc.save(pid, color, key)
            self._main_app.account = account
            self._main_app._refresh_login_status()
            cb = self._on_success
            self.destroy()
            if cb:
                cb()
        else:
            messagebox.showerror("登入失敗", result, parent=self)

    def _open_register(self):
        cb = self._on_success
        self.destroy()
        RegisterWindow(self._main_app, on_success=cb)


# --- 註冊視窗 ---
class RegisterWindow(tk.Toplevel):
    def __init__(self, main_app, on_success=None):
        super().__init__(main_app)
        self._main_app   = main_app
        self._on_success = on_success
        self.title("建立帳號")
        self.resizable(False, False)
        self.player_color = "#000000"

        tk.Label(self, text="玩家 ID:", font=("微軟正黑體", 11)).grid(
            row=0, column=0, padx=16, pady=10, sticky="e")
        self.id_entry = tk.Entry(self, width=22)
        self.id_entry.grid(row=0, column=1, padx=12, pady=10)

        tk.Label(self, text="ID 顏色:", font=("微軟正黑體", 11)).grid(
            row=1, column=0, padx=16, pady=6, sticky="e")
        self.color_btn = tk.Button(self, text="選擇顏色",
                                   bg=self.player_color, fg="white",
                                   command=self._pick_color)
        self.color_btn.grid(row=1, column=1, padx=12, pady=6, sticky="we")

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="註冊", width=9, command=self._on_register).pack(side="left", padx=8)
        tk.Button(btn_frame, text="取消", width=9, command=self.destroy).pack(side="left", padx=8)

        center_window(self)
        self.transient(main_app)
        self.grab_set()

    def _pick_color(self):
        color = colorchooser.askcolor(title="選擇玩家 ID 顏色", parent=self)[1]
        if color:
            color = GameSettingsDialog._darken_if_bright(color)
            self.player_color = color
            self.color_btn.config(bg=color)

    def _on_register(self):
        pid = self.id_entry.get().strip()
        if not pid:
            messagebox.showwarning("提示", "請輸入玩家 ID", parent=self)
            return
        recovery_key = acc.generate_recovery_key()
        key_hash     = acc.hash_key(recovery_key)
        ok, err = fb.register_user(pid, self.player_color, key_hash)
        if not ok:
            messagebox.showerror("註冊失敗", err, parent=self)
            return
        account = acc.save(pid, self.player_color, recovery_key)
        self._main_app.account = account
        self._main_app._refresh_login_status()
        cb = self._on_success
        self.destroy()
        RecoveryKeyDialog(self._main_app, recovery_key, on_close=cb)


# --- Recovery Key 提示視窗 ---
class RecoveryKeyDialog(tk.Toplevel):
    def __init__(self, parent, recovery_key: str, on_close=None):
        super().__init__(parent)
        self.title("請保存 Recovery Key")
        self.resizable(False, False)
        self._on_close = on_close

        tk.Label(self, text="請保存您的 Recovery Key",
                 font=("微軟正黑體", 12, "bold"), pady=14).pack()

        key_frame = tk.Frame(self, relief="ridge", bd=2, padx=20, pady=14)
        key_frame.pack(padx=24, pady=4)
        tk.Label(key_frame, text=recovery_key,
                 font=("Courier New", 16, "bold"), fg="#c0392b").pack()

        tk.Label(self,
                 text="此金鑰可用來在其他裝置登入。\n系統不會再次顯示，請立即備份。",
                 font=("微軟正黑體", 10), fg="gray", pady=10).pack()

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(0, 14))
        tk.Button(btn_frame, text="複製到剪貼簿", width=14,
                  command=lambda: self._copy(recovery_key)).pack(side="left", padx=8)
        tk.Button(btn_frame, text="我已備份，關閉", width=14,
                  command=self._close).pack(side="left", padx=8)

        center_window(self)
        self.transient(parent)
        self.grab_set()

    def _copy(self, key):
        self.clipboard_clear()
        self.clipboard_append(key)
        messagebox.showinfo("已複製", "Recovery Key 已複製到剪貼簿。", parent=self)

    def _close(self):
        cb = self._on_close
        self.destroy()
        if cb:
            cb()


# --- 主選單介面 ---
class MainMenu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("踩地雷 - 遊戲選單")
        self.geometry("600x450")
        center_window(self)
        self.account             = acc.load()  # 本機帳號 dict，未登入為 None
        self._status_item        = None        # Canvas 登入狀態文字 ID
        self._logout_btn_window  = None        # Canvas 登出按鈕視窗 ID
        self._current_bgm        = None        # 目前播放的背景音樂名稱
        self.last_player_id      = "Unknown"
        self.last_player_color   = "#000000"
        if self.account:
            self.last_player_id    = self.account["player_id"]
            self.last_player_color = self.account.get("color", "#000000")
        pygame.mixer.init()
        try:
            self.bg_image = ImageTk.PhotoImage(Image.open(ASSETS_DIR / "main_menu_bg.jpg").resize((600, 450)))
        except:
            self.bg_image = None
        self.show_main_menu()

    def show_main_menu(self):
        if hasattr(self, 'main_container'): self.main_container.destroy()
        self.geometry("600x450")
        if self._current_bgm != "menu":
            try:
                pygame.mixer.music.load(ASSETS_DIR / "menu_bgm.mp3")
                pygame.mixer.music.set_volume(0.5)
                pygame.mixer.music.play(-1)
                self._current_bgm = "menu"
            except: pass

        self.main_container = tk.Frame(self)
        self.main_container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.main_container, width=600, height=450, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        if self.bg_image: self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")
        else: self.canvas.configure(bg="#b0d8d2")

        self.canvas.create_text(300, 40, text="踩地雷", font=("Verdana", 28, "bold"), fill="#f2d235")
        self.canvas.create_text(298, 38, text="踩地雷", font=("Verdana", 28, "bold"), fill="#191512")

        self._status_item = None
        self._logout_btn_window = None
        self._draw_top_bar(show_logout=True)

        btn_style = {"font": ("微軟正黑體", 12, "bold"), "bg": "#8ea994", "fg": "white",
                     "width": 12, "bd": 3, "relief": "ridge", "cursor": "hand2"}

        menu_options = [
            ("新遊戲",   self._on_new_game),
            ("回放記錄", self._on_replay_records),
            ("查看排名", self._on_leaderboard),
            ("退出遊戲", self.quit)
        ]

        for i, (text, cmd) in enumerate(menu_options):
            btn = tk.Button(self.canvas, text=text, **btn_style, command=cmd)
            self.canvas.create_window(300, 150 + (i * 60), window=btn)

    def _draw_top_bar(self, show_logout=True):
        if self._status_item:
            self.canvas.delete(self._status_item)
            self._status_item = None
        if self._logout_btn_window:
            self.canvas.delete(self._logout_btn_window)
            self._logout_btn_window = None
        if self.account:
            pid   = self.account["player_id"]
            color = self.account.get("color", "#000000")
            if show_logout:
                logout_btn = tk.Button(
                    self.canvas, text="登出",
                    font=("微軟正黑體", 9, "bold"), bg="#8ea994", fg="white",
                    bd=2, relief="ridge", cursor="hand2", padx=4,
                    command=self._on_logout)
                self._logout_btn_window = self.canvas.create_window(
                    597, 6, window=logout_btn, anchor="ne")
                id_x = 544
            else:
                id_x = 597
            # 玩家 ID 以色塊呈現：底色為 ID 顏色，文字固定白色，確保在任意背景下可讀
            id_label = tk.Label(
                self.canvas, text=f" {pid} ",
                font=("微軟正黑體", 10, "bold"), bg=color, fg="white",
                padx=2, pady=1)
            self._status_item = self.canvas.create_window(
                id_x, 6, window=id_label, anchor="ne")
        else:
            self._status_item = self.canvas.create_text(
                597, 14, text="未登入", anchor="ne",
                font=("微軟正黑體", 10), fill="gray")

    def _refresh_login_status(self):
        if self.account:
            self.last_player_id    = self.account["player_id"]
            self.last_player_color = self.account.get("color", "#000000")
        if hasattr(self, 'canvas') and self.canvas.winfo_exists():
            self._draw_top_bar(show_logout=True)

    def _on_logout(self):
        if not self.account:
            return
        pid = self.account["player_id"]
        key = self.account.get("recovery_key", "")
        dlg = tk.Toplevel(self)
        dlg.title("確認登出")
        dlg.resizable(False, False)
        tk.Label(dlg, text=f"確定要登出「{pid}」嗎？",
                 font=("微軟正黑體", 11, "bold"), pady=8).pack(padx=20)
        tk.Label(dlg, text="請先備份你的 Recovery Key：",
                 font=("微軟正黑體", 10)).pack(padx=20)
        key_var = tk.StringVar(value=key)
        tk.Entry(dlg, textvariable=key_var, state="readonly",
                 font=("Courier", 11, "bold"), width=22, justify="center").pack(padx=20, pady=6)
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="複製 Key",
                  command=lambda: (dlg.clipboard_clear(), dlg.clipboard_append(key))).pack(side="left", padx=8)
        tk.Button(btn_frame, text="確認登出",
                  command=lambda: self._do_logout(dlg)).pack(side="left", padx=8)
        tk.Button(btn_frame, text="取消",
                  command=dlg.destroy).pack(side="left", padx=8)
        center_window(dlg)
        dlg.transient(self)
        dlg.grab_set()

    def _do_logout(self, dlg):
        dlg.destroy()
        acc.ACCOUNT_FILE.unlink(missing_ok=True)
        self.account = None
        self.last_player_id    = "Unknown"
        self.last_player_color = "#000000"
        self._refresh_login_status()

    def _on_new_game(self):
        if self.account is None:
            self.show_login_window(callback=self.show_difficulty_menu)
        else:
            self.show_difficulty_menu()

    def _on_leaderboard(self):
        if not fb.is_online():
            messagebox.showwarning("無法連線", "目前無法連線至伺服器，請確認網路連線後再試。")
            return
        LeaderboardWindow(self)

    def _on_replay_records(self):
        if not fb.is_online():
            messagebox.showwarning("無法連線", "目前無法連線至伺服器，請確認網路連線後再試。")
            return
        if self.account is None:
            self.show_login_window(callback=lambda: ReplayListWindow(self, self.account))
        else:
            ReplayListWindow(self, self.account)

    def show_login_window(self, callback=None):
        LoginWindow(self, on_success=callback)

    def show_difficulty_menu(self):
        self.main_container.destroy()
        self.main_container = tk.Frame(self)
        self.main_container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.main_container, width=600, height=450, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        if self.bg_image: self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")
        else: self.canvas.configure(bg="#b0d8d2")
        
        self.canvas.create_text(300, 40, text="請選擇難度", font=("微軟正黑體", 20, "bold"), fill="#f2d235")
        self.canvas.create_text(298, 38, text="請選擇難度", font=("微軟正黑體", 20, "bold"), fill="#191512")
        
        btn_style = {"font": ("微軟正黑體", 12, "bold"), "bg": "#8ea994", "fg": "white", "width": 8, "bd": 3, "relief": "ridge", "cursor": "hand2"}
        difficulties = [("簡單", 8, 8, 10), ("普通", 12, 12, 30), ("困難", 16, 16, 60)]
        
        for i, (text, r, c, m) in enumerate(difficulties):
            btn = tk.Button(self.canvas, text=text, **btn_style, command=lambda r=r, c=c, m=m: self.pre_game_setup(r, c, m, False))
            self.canvas.create_window(150 + (i * 150), 150, window=btn)
            
        custom_btn = tk.Button(self.canvas, text="自訂", **btn_style, command=lambda: self.pre_game_setup(20, 20, 50, True))
        self.canvas.create_window(300, 220, window=custom_btn)

        back_btn = tk.Button(self.canvas, text="返回主選單", font=("微軟正黑體", 10), bg="#95a5a6", fg="white", command=self.show_main_menu)
        self.canvas.create_window(520, 410, window=back_btn)

        self._status_item = None
        self._logout_btn_window = None
        self._draw_top_bar(show_logout=False)

    # 非自訂難度直接開始；自訂模式開啟設定對話框（不含玩家 ID / 顏色欄位）
    def pre_game_setup(self, r, c, m, is_custom):
        if not is_custom:
            self.start_game(r, c, m, self.last_player_id, self.last_player_color, radar_uses=2)
        else:
            dialog = GameSettingsDialog(self, r, c, m, is_custom=True,
                                        default_id=self.last_player_id,
                                        default_color=self.last_player_color,
                                        show_player_fields=False)
            if dialog.result:
                r, c, m, p_id, p_color, radar_uses = dialog.result
                self.start_game(r, c, m, p_id, p_color, radar_uses)

    # 停止主選單音樂，建立遊戲邏輯與介面，並將視窗重新置中
    def start_game(self, r, c, m, p_id, p_color, radar_uses):
        pygame.mixer.music.stop()
        self._current_bgm = None
        if hasattr(self, 'main_container'): self.main_container.destroy()
        self.geometry("")
        game_logic = MinesweeperLogic(r, c, m)
        self.game_ui = MinesweeperUI(self, game_logic, p_id, p_color, radar_uses, self.show_main_menu)
        center_window(self)

    # 從 Replay 檔案建立邏輯層並直接啟動回放（略過 reset_board，直接載入儲存的 board）
    def play_replay(self, data):
        pygame.mixer.music.stop()
        self._current_bgm = None
        if hasattr(self, 'main_container'): self.main_container.destroy()
        self.geometry("")
        s = data["settings"]
        logic = MinesweeperLogic(s["rows"], s["cols"], s["mines"])
        logic.board = data["board"]
        logic.revealed = [[False] * s["cols"] for _ in range(s["rows"])]
        logic.first_click = False
        meta = data["meta"]
        history = [tuple(h) for h in data["history"]]
        self.game_ui = MinesweeperUI(self, logic, meta["player_id"], meta["player_color"],
                                     s.get("radar_uses", 2), self.show_main_menu)
        self.game_ui.start_replay(history=history)
        center_window(self)

if __name__ == "__main__":
    app = MainMenu()
    app.mainloop()
