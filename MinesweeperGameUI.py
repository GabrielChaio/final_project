import tkinter as tk
from tkinter import messagebox, colorchooser, ttk
from PIL import Image, ImageTk
import random
import pygame
import json
from collections import deque
from datetime import datetime

MAX_GENERATION_ATTEMPTS = 1000  # 地圖生成失敗保護：超過此次數則回報錯誤
DIFFICULTY_PRESETS = {(8, 8, 10): "easy", (12, 12, 30): "normal", (16, 16, 60): "hard"}

# ---排行榜管理---
class LeaderboardManager:
    FILEPATH = "leaderboard.json"

    @staticmethod
    def _empty():
        return {
            "easy":   {"normal": [], "no_tool": [], "no_tool_no_flag": []},
            "normal": {"normal": [], "no_tool": [], "no_tool_no_flag": []},
            "hard":   {"normal": [], "no_tool": [], "no_tool_no_flag": []}
        }

    @staticmethod
    def load():
        try:
            with open(LeaderboardManager.FILEPATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return LeaderboardManager._empty()
        except Exception:
            messagebox.showerror("排行榜錯誤", "leaderboard.json 損毀，已重建空排行榜。")
            return LeaderboardManager._empty()

    @staticmethod
    def save(data):
        with open(LeaderboardManager.FILEPATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def add_record(difficulty, category, player_id, time_sec):
        data = LeaderboardManager.load()
        data[difficulty][category].append({
            "player_id": player_id,
            "time": time_sec,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        data[difficulty][category].sort(key=lambda x: x["time"])
        data[difficulty][category] = data[difficulty][category][:10]
        LeaderboardManager.save(data)

    @staticmethod
    def get_records(difficulty, category):
        return LeaderboardManager.load().get(difficulty, {}).get(category, [])

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
    def __init__(self, parent, default_r=8, default_c=8, default_m=8, is_custom=False):
        super().__init__(parent)
        self.title("遊戲設定")
        self.is_custom = is_custom
        self.result = None
        self.player_color = "#000000"
        
        tk.Label(self, text="玩家 ID:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.id_entry = tk.Entry(self)
        self.id_entry.insert(0, "Unknown")
        self.id_entry.grid(row=0, column=1, padx=10, pady=5)
        
        tk.Label(self, text="ID 顏色:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.color_btn = tk.Button(self, text="選擇顏色", bg=self.player_color, fg="white", command=self.pick_color)
        self.color_btn.grid(row=1, column=1, padx=10, pady=5, sticky="we")

        # 預設探測器使用次數為 2
        self.radar_val = 2

        if is_custom:
            tk.Label(self, text="列數 (5-27):").grid(row=2, column=0, padx=10, pady=5, sticky="e")
            self.r_entry = tk.Entry(self)
            self.r_entry.insert(0, str(default_r))
            self.r_entry.grid(row=2, column=1, padx=10, pady=5)

            tk.Label(self, text="行數 (5-44):").grid(row=3, column=0, padx=10, pady=5, sticky="e")
            self.c_entry = tk.Entry(self)
            self.c_entry.insert(0, str(default_c))
            self.c_entry.grid(row=3, column=1, padx=10, pady=5)

            self.mine_range_label = tk.Label(self, text="地雷數量:")
            self.mine_range_label.grid(row=4, column=0, padx=10, pady=5, sticky="e")
            self.m_entry = tk.Entry(self)
            self.m_entry.insert(0, str(default_m))
            self.m_entry.grid(row=4, column=1, padx=10, pady=5)

            tk.Label(self, text="探測器次數:").grid(row=5, column=0, padx=10, pady=5, sticky="e")
            self.radar_entry = tk.Entry(self)
            self.radar_entry.insert(0, "2")
            self.radar_entry.grid(row=5, column=1, padx=10, pady=5)

            # 綁定列數與行數輸入框，即時更新地雷數量範圍標籤
            self.r_entry.bind("<KeyRelease>", self._update_mine_range_label)
            self.c_entry.bind("<KeyRelease>", self._update_mine_range_label)
            self._update_mine_range_label()
        else:
            self.r_val, self.c_val, self.m_val = default_r, default_c, default_m

        tk.Button(self, text="開始遊戲", command=self.on_confirm).grid(row=6, column=0, columnspan=2, pady=10)
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
        p_id = self.id_entry.get().strip() or "Unknown"
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
        self.logic = logic
        self.player_id = player_id
        self.player_color = player_color
        self.on_close_callback = on_close_callback
        self.buttons = []
        self.start_time = 0
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
            pygame.mixer.music.load("game_bgm.mp3") 
            pygame.mixer.music.set_volume(0.5)
            pygame.mixer.music.play(-1)
            self.click_sound = pygame.mixer.Sound("click.mp3")
            self.boom_sound = pygame.mixer.Sound("boom.mp3")
            self.radar_sound = pygame.mixer.Sound("radar.mp3") 
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
        if not from_replay: self.history.append(('click', r, c))

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
            self.timer_running = True
            self.update_timer()
            
        if self.logic.board[r][c] == -1:
            if self.boom_sound and not self.is_replaying: self.boom_sound.play()
            self.timer_running = False
            self.buttons[r][c].config(text="💣", bg="red")
            if not from_replay: self.end_game_flow(f"玩家: {self.player_id}\n踩到地雷了！耗時: {self.start_time} 秒")
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
            self.history.append(('flag', r, c))
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
            self.history.append(('auto_reveal', r, c))
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
                    if not from_replay: self.end_game_flow(f"玩家: {self.player_id}\n踩到地雷了！耗時: {self.start_time} 秒")
                    return
                else:
                    self.expand(nr, nc)
        if not from_replay: self.check_win()

    # 顯示自訂結束對話框，提供「查看回放」與「返回主選單」兩個選項
    def show_custom_end_dialog(self, message):
        dialog = tk.Toplevel(self)
        dialog.title("遊戲結束")
        dialog.geometry("300x150")
        center_window(dialog)
        dialog.transient(self)
        dialog.grab_set()
        tk.Label(dialog, text=message, font=("微軟正黑體", 11), pady=20).pack()
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="查看回放", width=12, command=lambda: [dialog.destroy(), self.start_replay()]).pack(side="left", padx=10)
        tk.Button(btn_frame, text="返回主選單", width=12, command=lambda: [dialog.destroy(), self.exit_game()]).pack(side="left", padx=10)
    
    # 遊戲結束流程：停止計時並顯示結果對話框
    def end_game_flow(self, message):
        self.timer_running = False 
        if self.history: self.show_custom_end_dialog(message)
        else:
            messagebox.showinfo("遊戲結束", message)
            self.exit_game()

    # 重置盤面視覺狀態並進入回放模式
    def start_replay(self):
        self.is_replaying = True
        self.timer_running = False
        self.radar_mines = set()
        self.flag_count = 0
        self.logic.revealed = [[False for _ in range(self.logic.cols)] for _ in range(self.logic.rows)]
        for r in range(self.logic.rows):
            for c in range(self.logic.cols):
                self.buttons[r][c].config(text="", bg="SystemButtonFace", state=tk.NORMAL, relief=tk.RAISED)
        self.start_time = 0
        self.timer_label.config(text="回放中...")
        self.replay_step(0)

    # 逐步重播 history 中的每個操作，每步間隔 500ms
    def replay_step(self, index):
        if not self.winfo_exists(): return 
        if index < len(self.history):
            record = self.history[index]
            action = record[0]
            if action == 'click':
                r, c = record[1], record[2]
                if self.logic.board[r][c] == -1: self.buttons[r][c].config(text="💣", bg="red")
                else: self.expand(r, c)
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
            self.after(500, lambda: self.replay_step(index + 1))
        else:
            self.is_replaying = False
            messagebox.showinfo("回放", "回放結束")
            self.exit_game()

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
            self._save_score()
            self.end_game_flow(f"勝利！恭喜 {self.player_id}！\n總耗時: {self.start_time} 秒")

    # 依難度與挑戰限制將本局成績寫入排行榜（自訂模式不入榜）
    def _save_score(self):
        difficulty = DIFFICULTY_PRESETS.get((self.logic.rows, self.logic.cols, self.logic.mines_count))
        if difficulty is None:
            return
        LeaderboardManager.add_record(difficulty, "normal", self.player_id, self.start_time)
        if self.radar_used_count == 0:
            LeaderboardManager.add_record(difficulty, "no_tool", self.player_id, self.start_time)
            if self.flag_used_count == 0:
                LeaderboardManager.add_record(difficulty, "no_tool_no_flag", self.player_id, self.start_time)

    # 執行金屬探測器效果，依模式揭示十字或九宮格範圍內的所有格子
    def use_radar(self, r, c, mode):
        if self.radar_sound and not self.is_replaying: self.radar_sound.play()
        if not self.is_replaying:
            self.history.append(('radar', r, c, mode))
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

    # 每秒遞增計時器並更新顯示標籤，timer_running 為 False 時自動停止
    def update_timer(self):
        if self.timer_running:
            self.start_time += 1
            self.timer_label.config(text=f"時間: {self.start_time} 秒")
            self.after(1000, self.update_timer)

    # 停止背景音樂、銷毀遊戲介面並執行返回主選單的回呼函式
    def exit_game(self):
        pygame.mixer.music.stop()
        self.destroy()
        self.on_close_callback()

# --- 排行榜視窗 ---
class LeaderboardWindow(tk.Toplevel):
    _DIFF = {"簡單": "easy", "普通": "normal", "困難": "hard"}
    _CAT  = {"無限制": "normal", "無道具": "no_tool", "無道具無旗子": "no_tool_no_flag"}

    def __init__(self, parent):
        super().__init__(parent)
        self.title("排行榜")
        self.resizable(False, False)

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
                                 show="headings", height=10)
        for col, label, w in [("rank", "排名", 50), ("player", "玩家 ID", 120),
                               ("time", "時間", 80), ("date", "日期", 120)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=w, anchor="center")
        self.tree.pack(padx=12, pady=(0, 12))

        self.refresh()
        center_window(self)
        self.transient(parent)

    def refresh(self):
        records = LeaderboardManager.get_records(
            self._DIFF[self.diff_var.get()], self._CAT[self.cat_var.get()])
        self.tree.delete(*self.tree.get_children())
        for i, rec in enumerate(records, 1):
            self.tree.insert("", "end", values=(
                i, rec["player_id"], f"{rec['time']} 秒", rec["date"][:10]))

# --- 主選單介面 ---
class MainMenu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("踩地雷 - 遊戲選單")
        self.geometry("600x450")
        center_window(self)
        pygame.mixer.init()
        try:
            self.bg_image = ImageTk.PhotoImage(Image.open("main_menu_bg.jpg").resize((600, 450)))
        except:
            self.bg_image = None
        self.show_main_menu()

    #顯示主選單
    def show_main_menu(self):
        if hasattr(self, 'main_container'): self.main_container.destroy()
        self.geometry("600x450")
        try:
            pygame.mixer.music.load("menu_bgm.mp3") 
            pygame.mixer.music.set_volume(0.5)
            pygame.mixer.music.play(-1)
        except: pass
        
        self.main_container = tk.Frame(self)
        self.main_container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.main_container, width=600, height=450, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        if self.bg_image: self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")
        else: self.canvas.configure(bg="#b0d8d2")
        
        # 用兩個標題重疊陰影效果
        self.canvas.create_text(300, 40, text="踩地雷", font=("Verdana", 28, "bold"), fill="#f2d235")
        self.canvas.create_text(298, 38, text="踩地雷", font=("Verdana", 28, "bold"), fill="#191512")
        
        btn_style = {"font": ("微軟正黑體", 12, "bold"), "bg": "#8ea994", "fg": "white", "width": 12, "bd": 3, "relief": "ridge", "cursor": "hand2"}
        
        # 主選單按鈕
        menu_options = [
            ("新遊戲", self.show_difficulty_menu),
            ("載入遊戲", lambda: messagebox.showinfo("提示", "交給你了")),
            ("查看排名", lambda: LeaderboardWindow(self)),
            ("退出遊戲", self.quit)
        ]
        
        for i, (text, cmd) in enumerate(menu_options):
            btn = tk.Button(self.canvas, text=text, **btn_style, command=cmd)
            self.canvas.create_window(300, 150 + (i * 60), window=btn)

    #難度選擇
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

    # 開啟設定對話框並依回傳結果啟動遊戲
    def pre_game_setup(self, r, c, m, is_custom):
        dialog = GameSettingsDialog(self, r, c, m, is_custom)
        if dialog.result:
            r, c, m, p_id, p_color, radar_uses = dialog.result
            self.start_game(r, c, m, p_id, p_color, radar_uses)

    # 停止主選單音樂，建立遊戲邏輯與介面，並將視窗重新置中
    def start_game(self, r, c, m, p_id, p_color, radar_uses):
        pygame.mixer.music.stop()
        if hasattr(self, 'main_container'): self.main_container.destroy()
        self.geometry("") 
        game_logic = MinesweeperLogic(r, c, m)
        self.game_ui = MinesweeperUI(self, game_logic, p_id, p_color, radar_uses, self.show_main_menu)
        center_window(self)

if __name__ == "__main__":
    app = MainMenu()
    app.mainloop()