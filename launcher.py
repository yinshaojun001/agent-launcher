#!/usr/bin/env python3
"""
agent-launcher: Pokemon-style TUI launcher for Codex and Claude Code.
Split-screen layout: left = game map, right = status panel.
"""

import curses
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

CODEX_DIR       = Path.home() / ".codex"
CLAUDE_DIR      = Path.home() / ".claude"
CODEX_CONFIG    = CODEX_DIR / "config.toml"
CODEX_AUTH      = CODEX_DIR / "auth.json"
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"
PROFILES_FILE   = Path.home() / ".agent-launcher" / "profiles.json"
BACKUP_DIR      = Path.home() / ".agent-launcher" / "backups"

CODEX_BIN  = shutil.which("codex") or "/Applications/Codex.app/Contents/Resources/codex"
CLAUDE_BIN = shutil.which("claude-tap") or shutil.which("claude") or "claude-tap"

# ─── Color pairs ──────────────────────────────────────────────────────────────

# Pair IDs
P_NORMAL    = 0
P_PLAYER    = 1
P_BALL      = 2
P_GRASS     = 3
P_WATER     = 4
P_TREE      = 5
P_PATH      = 6
P_ORANGE    = 7   # main border / title
P_CYAN      = 8   # secondary border
P_GREEN     = 9   # active / ok
P_DIM       = 10  # dimmed text
P_STATUSBAR = 11  # bottom bar
P_DIALOG    = 12  # dialog bg
P_YELLOW    = 13  # highlight
P_RED       = 14  # delete / warn
P_CODEX     = 15
P_CLAUDE    = 16
P_PANEL     = 17  # right panel bg tint

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(P_PLAYER,    curses.COLOR_WHITE,   -1)
    curses.init_pair(P_BALL,      curses.COLOR_RED,     -1)
    curses.init_pair(P_GRASS,     curses.COLOR_GREEN,   -1)
    curses.init_pair(P_WATER,     curses.COLOR_BLUE,    -1)
    curses.init_pair(P_TREE,      curses.COLOR_GREEN,   -1)
    curses.init_pair(P_PATH,      curses.COLOR_YELLOW,  -1)
    curses.init_pair(P_ORANGE,    curses.COLOR_YELLOW,  -1)   # closest to orange
    curses.init_pair(P_CYAN,      curses.COLOR_CYAN,    -1)
    curses.init_pair(P_GREEN,     curses.COLOR_GREEN,   -1)
    curses.init_pair(P_DIM,       8,                    -1)
    curses.init_pair(P_STATUSBAR, curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(P_DIALOG,    curses.COLOR_WHITE,   curses.COLOR_BLACK)
    curses.init_pair(P_YELLOW,    curses.COLOR_YELLOW,  -1)
    curses.init_pair(P_RED,       curses.COLOR_RED,     -1)
    curses.init_pair(P_CODEX,     curses.COLOR_MAGENTA, -1)
    curses.init_pair(P_CLAUDE,    curses.COLOR_CYAN,    -1)
    curses.init_pair(P_PANEL,     curses.COLOR_WHITE,   -1)

# ─── Map definition ───────────────────────────────────────────────────────────

T_GRASS = '.'
T_TREE  = 'T'
T_WATER = '~'
T_PATH  = 'P'
T_WALL  = '#'

RAW_MAP = [
    "################################",
    "#TTTTTTTTTTTTTTTTTTTTTTTTTTTTTT#",
    "#T............................T#",
    "#T...PPPP.................T...T#",
    "#T...P..P.................T...T#",
    "#T...PPPP.................T...T#",
    "#T............................T#",
    "#T.......~~~~.................T#",
    "#T.......~~~~.................T#",
    "#T............................T#",
    "#T............................T#",
    "#T......................PPPP..T#",
    "#T......................P..P..T#",
    "#T......................PPPP..T#",
    "#T............................T#",
    "#T............................T#",
    "#TTTTTTTTTTTTTTTTTTTTTTTTTTTTTT#",
    "################################",
]
MAP_ROWS = len(RAW_MAP)
MAP_COLS = len(RAW_MAP[0])

TILE_CHAR = {T_GRASS: '░', T_TREE: '♣', T_WATER: '≈', T_PATH: '·', T_WALL: '▓'}
TILE_COLOR = {T_GRASS: P_GRASS, T_TREE: P_TREE, T_WATER: P_WATER, T_PATH: P_PATH, T_WALL: P_DIM}

def walkable(r, c):
    if 0 <= r < MAP_ROWS and 0 <= c < MAP_COLS:
        return RAW_MAP[r][c] in (T_GRASS, T_PATH)
    return False

# ─── Player sprites ───────────────────────────────────────────────────────────

# 3×3, two walk frames, four directions
SPRITES = {
    'down':  [["(˶ᵔ ᵕ ᵔ˶)", " (っ づ)", "  ∪ ∪  "],
              ["(˶ᵔ ᵕ ᵔ˶)", "  づっ) ", "  ∪ ∪  "]],
    'up':    [["  ∩ ∩  ", " (っ づ)", "(˵¯ᗜ¯˵)"],
              ["  ∩ ∩  ", "  づっ) ", "(˵¯ᗜ¯˵)"]],
    'left':  [["  ∩ ∩  ", "(っ づ  ", "(˵¯ᗜ¯˵)"],
              ["  ∩ ∩  ", "(っ づ  ", "(˵ᵔᗜᵔ˵)"]],
    'right': [["∩ ∩    ", "  づっ) ", "(˵¯ᗜ¯˵)"],
              ["∩ ∩    ", "  づっ) ", "(˵ᵔᗜᵔ˵)"]],
}
SPRITE_W = 9  # chars wide
SPRITE_H = 3

# Pokeball glyphs (one cell each, blink between two)
BALL_GLYPHS = ["🔮", "✨"]

# ─── Data layer ───────────────────────────────────────────────────────────────

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default

def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))
    p.chmod(0o600)

def load_profiles():
    return load_json(PROFILES_FILE, [])

def save_profiles(profiles):
    save_json(PROFILES_FILE, profiles)

def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for src in [CODEX_CONFIG, CODEX_AUTH, CLAUDE_SETTINGS]:
        if src.exists():
            shutil.copy(src, BACKUP_DIR / f"{src.name}.{ts}")

def active_codex_url():
    try:
        m = re.search(r'^base_url\s*=\s*"([^"]+)"',
                      CODEX_CONFIG.read_text(), re.MULTILINE)
        return m.group(1) if m else ""
    except Exception:
        return ""

def active_claude_url():
    try:
        d = load_json(CLAUDE_SETTINGS, {})
        env = d.get("env") or d.get("shell_environment_policy", {}).get("set", {})
        return env.get("ANTHROPIC_BASE_URL", "")
    except Exception:
        return ""

def apply_codex(url, key):
    if not url or not key:
        return
    backup()
    text = CODEX_CONFIG.read_text()
    text = re.sub(r'^base_url\s*=.*',              f'base_url = "{url}"',              text, flags=re.MULTILINE)
    text = re.sub(r'^preferred_auth_method\s*=.*', 'preferred_auth_method = "apikey"', text, flags=re.MULTILINE)
    text = re.sub(r'^model_provider\s*=.*',        'model_provider = "custom"',        text, flags=re.MULTILINE)
    CODEX_CONFIG.write_text(text)
    save_json(CODEX_AUTH, {"auth_mode": "apikey", "OPENAI_API_KEY": key})

def apply_claude(url, key):
    if not url or not key:
        return
    backup()
    settings = load_json(CLAUDE_SETTINGS, {})
    if "env" in settings:
        settings["env"]["ANTHROPIC_BASE_URL"]   = url
        settings["env"]["ANTHROPIC_AUTH_TOKEN"] = key
    else:
        sp = settings.setdefault("shell_environment_policy", {})
        s  = sp.setdefault("set", {})
        s["ANTHROPIC_BASE_URL"]   = url
        s["ANTHROPIC_AUTH_TOKEN"] = key
    save_json(CLAUDE_SETTINGS, settings)

# ─── Drawing primitives ───────────────────────────────────────────────────────

def safe_add(win, y, x, text, attr=0):
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        win.addstr(y, x, text[:max(0, w - x - 1)], attr)
    except curses.error:
        pass

def draw_border(win, y, x, h, w, color_pair, title=""):
    """Draw a rounded box with colored border."""
    a = curses.color_pair(color_pair) | curses.A_BOLD
    try:
        win.addstr(y,     x,     "╭" + "─"*(w-2) + "╮", a)
        win.addstr(y+h-1, x,     "╰" + "─"*(w-2) + "╯", a)
        for i in range(1, h-1):
            win.addstr(y+i, x,     "│", a)
            win.addstr(y+i, x+w-1, "│", a)
    except curses.error:
        pass
    if title:
        t = f" {title} "
        safe_add(win, y, x+2, t, curses.color_pair(color_pair) | curses.A_BOLD)

def fill_rect(win, y, x, h, w, ch=' ', attr=0):
    for r in range(y, y+h):
        safe_add(win, r, x, ch * w, attr)

# ─── Dialog system ────────────────────────────────────────────────────────────

def typewriter(win, y, x, text, attr, delay=0.018):
    for i, ch in enumerate(text):
        safe_add(win, y, x+i, ch, attr)
        win.refresh()
        time.sleep(delay)

def dialog_box(stdscr, lines, wait=True):
    h, w = stdscr.getmaxyx()
    bh = len(lines) + 4
    bw = min(w - 6, max(44, max(len(l) for l in lines) + 6))
    by = h - bh - 2
    bx = (w - bw) // 2
    attr = curses.color_pair(P_DIALOG)

    fill_rect(stdscr, by, bx, bh, bw, ' ', attr)
    draw_border(stdscr, by, bx, bh, bw, P_ORANGE)
    for i, line in enumerate(lines):
        typewriter(stdscr, by+2+i, bx+3, line[:bw-6], attr, delay=0.018)

    if wait:
        safe_add(stdscr, by+bh-1, bx+bw-4, "▼ ",
                 curses.color_pair(P_ORANGE) | curses.A_BOLD)
        stdscr.refresh()
        while stdscr.getch() not in (10, 13, ord(' ')):
            pass

def choice_dialog(stdscr, title, options):
    """Returns selected index or -1."""
    h, w = stdscr.getmaxyx()
    bh = len(options) + 5
    bw = min(w - 6, max(36, max(len(o) for o in options) + 10))
    by = h - bh - 2
    bx = (w - bw) // 2

    idx = 0
    while True:
        attr = curses.color_pair(P_DIALOG)
        fill_rect(stdscr, by, bx, bh, bw, ' ', attr)
        draw_border(stdscr, by, bx, bh, bw, P_CYAN, title)
        for i, opt in enumerate(options):
            pfx = "▶ " if i == idx else "  "
            row_attr = attr | curses.A_BOLD if i == idx else attr
            safe_add(stdscr, by+2+i, bx+3, (pfx + opt)[:bw-5], row_attr)
        safe_add(stdscr, by+bh-1, bx+2,
                 "↑↓ move   Enter select   Esc cancel",
                 curses.color_pair(P_DIM))
        stdscr.refresh()

        k = stdscr.getch()
        if k in (curses.KEY_UP, ord('w'), ord('k')):
            idx = (idx - 1) % len(options)
        elif k in (curses.KEY_DOWN, ord('s'), ord('j')):
            idx = (idx + 1) % len(options)
        elif k in (10, 13, ord(' ')):
            return idx
        elif k == 27:
            return -1

def input_dialog(stdscr, prompt, default="", secret=False):
    h, w = stdscr.getmaxyx()
    bh, bw = 6, min(w-6, 64)
    by = h - bh - 2
    bx = (w - bw) // 2
    attr = curses.color_pair(P_DIALOG)

    curses.curs_set(1)
    val = list(default)
    while True:
        fill_rect(stdscr, by, bx, bh, bw, ' ', attr)
        draw_border(stdscr, by, bx, bh, bw, P_CYAN, "Edit")
        safe_add(stdscr, by+2, bx+3, prompt[:bw-6], attr | curses.A_BOLD)
        disp = ("*" * len(val)) if secret else "".join(val)
        safe_add(stdscr, by+3, bx+3, disp[:bw-6], attr)
        safe_add(stdscr, by+bh-1, bx+2,
                 "Enter confirm   Esc cancel", curses.color_pair(P_DIM))
        try:
            stdscr.move(by+3, bx+3+min(len(disp), bw-7))
        except curses.error:
            pass
        stdscr.refresh()

        k = stdscr.getch()
        if k in (10, 13):
            curses.curs_set(0)
            return "".join(val)
        elif k == 27:
            curses.curs_set(0)
            return ""
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            if val:
                val.pop()
        elif 32 <= k <= 126:
            val.append(chr(k))

# ─── Launch animation ─────────────────────────────────────────────────────────

def launch_animation(stdscr, agent, profile_name):
    h, w = stdscr.getmaxyx()
    cy, cx = h // 2, w // 2

    # White flash
    for _ in range(4):
        try:
            stdscr.bkgd(' ', curses.color_pair(P_STATUSBAR))
            stdscr.clear(); stdscr.refresh(); time.sleep(0.07)
            stdscr.bkgd(' ', 0)
            stdscr.clear(); stdscr.refresh(); time.sleep(0.07)
        except curses.error:
            pass

    stdscr.clear()
    color = P_CODEX if "codex" in agent.lower() else P_CLAUDE
    icon  = "🤖" if "codex" in agent.lower() else "🤖"

    frames = [
        ["  ╭───╮  ", " ▐◉───▌ ", "  ╰───╯  "],
        ["  ╭───╮  ", " ▐ ✦── ▌", "  ╰───╯  "],
        ["  ╭───╮  ", " ▐  ✦  ▌", "  ╰───╯  "],
        ["   ✦✦✦   ", "  ✦   ✦  ", "   ✦✦✦   "],
    ]
    for frame in frames:
        for i, row in enumerate(frame):
            safe_add(stdscr, cy-1+i, cx-5, row,
                     curses.color_pair(P_BALL) | curses.A_BOLD)
        stdscr.refresh()
        time.sleep(0.25)

    stdscr.clear()
    msg1 = f"  ✨ {agent} activated! ✨  "
    msg2 = f"  Profile: {profile_name}  "
    msg3 = "  Launching...  "
    safe_add(stdscr, cy-1, cx - len(msg1)//2, msg1,
             curses.color_pair(color) | curses.A_BOLD)
    safe_add(stdscr, cy,   cx - len(msg2)//2, msg2,
             curses.color_pair(P_YELLOW) | curses.A_BOLD)
    safe_add(stdscr, cy+1, cx - len(msg3)//2, msg3,
             curses.color_pair(P_DIM))
    stdscr.refresh()
    time.sleep(1.0)

# ─── Profile editor ───────────────────────────────────────────────────────────

def edit_profile_screen(stdscr, profile):
    p = {
        "name":       profile.get("name", ""),
        "codex_url":  (profile.get("codex")  or {}).get("url", ""),
        "codex_key":  (profile.get("codex")  or {}).get("key", ""),
        "claude_url": (profile.get("claude") or {}).get("url", ""),
        "claude_key": (profile.get("claude") or {}).get("key", ""),
    }
    FIELDS = [
        ("name",       "Profile name",   False),
        ("codex_url",  "Codex URL",      False),
        ("codex_key",  "Codex API Key",  True),
        ("claude_url", "Claude URL",     False),
        ("claude_key", "Claude API Key", True),
    ]
    cursor = 0
    curses.curs_set(0)

    SECTION_ROWS = {0: 0, 1: 2, 2: 3, 3: 5, 4: 6}  # field → content row offset

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        bw = min(68, w - 4)
        bh = 14
        by = max(1, (h - bh) // 2)
        bx = (w - bw) // 2

        attr = curses.color_pair(P_DIALOG)
        fill_rect(stdscr, by, bx, bh, bw, ' ', attr)
        draw_border(stdscr, by, bx, bh, bw, P_ORANGE, "✦ Edit Profile ✦")

        # Sections
        safe_add(stdscr, by+2,  bx+2, "── 🌟 General " + "─"*(bw-18), curses.color_pair(P_YELLOW) | curses.A_BOLD)
        safe_add(stdscr, by+5,  bx+2, "── 🤖 Codex   " + "─"*(bw-18), curses.color_pair(P_CODEX)  | curses.A_BOLD)
        safe_add(stdscr, by+8,  bx+2, "── 🧠 Claude  " + "─"*(bw-18), curses.color_pair(P_CLAUDE) | curses.A_BOLD)

        row_positions = [by+3, by+6, by+7, by+9, by+10]

        for fi, row in enumerate(row_positions):
            key_name, label, secret = FIELDS[fi]
            val = p[key_name]
            display = ("*" * min(len(val), 16) if secret and val else val) or "(empty)"
            is_sel  = fi == cursor
            pfx     = "  ▶ " if is_sel else "    "
            row_attr = attr | curses.A_BOLD if is_sel else attr
            safe_add(stdscr, row, bx+2,
                     f"{pfx}{label:<14}  {display[:bw-28]}", row_attr)
            if is_sel:
                safe_add(stdscr, row, bx+bw-8, "← Enter",
                         curses.color_pair(P_CYAN))

        safe_add(stdscr, by+bh-1, bx+2,
                 "↑↓ move   Enter edit   S save   Esc cancel",
                 curses.color_pair(P_DIM))
        stdscr.refresh()

        k = stdscr.getch()
        if k in (curses.KEY_UP, ord('k')):
            cursor = (cursor - 1) % len(FIELDS)
        elif k in (curses.KEY_DOWN, ord('j')):
            cursor = (cursor + 1) % len(FIELDS)
        elif k in (10, 13):
            key_name, label, secret = FIELDS[cursor]
            new_val = input_dialog(stdscr, f"{label}:", p[key_name], secret)
            if new_val is not None:
                p[key_name] = new_val
        elif k in (ord('s'), ord('S')):
            if not p["name"]:
                dialog_box(stdscr, ["⚠  Profile name cannot be empty!"])
                continue
            return {
                "name":   p["name"],
                "codex":  {"url": p["codex_url"],  "key": p["codex_key"]},
                "claude": {"url": p["claude_url"], "key": p["claude_key"]},
            }
        elif k == 27:
            return None

def manage_profiles_screen(stdscr):
    while True:
        profiles = load_profiles()
        cu = active_codex_url()
        cl = active_claude_url()
        idx = 0

        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            items = []
            for p in profiles:
                ca = "●" if (p.get("codex")  or {}).get("url") == cu and cu else "○"
                la = "●" if (p.get("claude") or {}).get("url") == cl and cl else "○"
                items.append(f"{p['name']}   🤖{ca}  🧠{la}")
            items.append("  ✦ New profile")

            bh = min(len(items) + 6, h - 2)
            bw = min(max(44, max(len(s) for s in items) + 10), w - 4)
            by = max(0, (h - bh) // 2)
            bx = max(0, (w - bw) // 2)

            attr = curses.color_pair(P_DIALOG)
            fill_rect(stdscr, by, bx, bh, bw, ' ', attr)
            draw_border(stdscr, by, bx, bh, bw, P_ORANGE, "✦ Profiles ✦")

            for i, item in enumerate(items):
                row = by + 2 + i
                if row >= by + bh - 1:
                    break
                is_sel   = i == idx
                row_attr = attr | curses.A_BOLD if is_sel else attr
                pfx      = "▶ " if is_sel else "  "
                safe_add(stdscr, row, bx+2, (pfx + item)[:bw-4], row_attr)

            safe_add(stdscr, by+bh-1, bx+2,
                     "Enter edit   D delete   Esc back",
                     curses.color_pair(P_DIM))
            stdscr.refresh()

            k = stdscr.getch()
            if k in (curses.KEY_UP, ord('k')):
                idx = (idx - 1) % len(items)
            elif k in (curses.KEY_DOWN, ord('j')):
                idx = (idx + 1) % len(items)
            elif k in (10, 13):
                if idx == len(profiles):
                    result = edit_profile_screen(stdscr, {})
                    if result:
                        profiles.append(result)
                        save_profiles(profiles)
                else:
                    result = edit_profile_screen(stdscr, profiles[idx])
                    if result:
                        profiles[idx] = result
                        save_profiles(profiles)
                break
            elif k in (ord('d'), ord('D')) and idx < len(profiles):
                name = profiles[idx]["name"]
                profiles.pop(idx)
                save_profiles(profiles)
                dialog_box(stdscr, [f"🗑  Deleted: {name}"], wait=False)
                time.sleep(0.5)
                break
            elif k in (ord('q'), 27):
                return

# ─── Game world ───────────────────────────────────────────────────────────────

BALL_POSITIONS = [
    (4, 6), (7, 22), (11, 8), (13, 24),
    (3, 16), (9, 4), (14, 14), (6, 28),
]

class GameState:
    def __init__(self, profiles):
        self.px, self.py = 14, 9   # player col, row
        self.direction = 'down'
        self.frame = 0
        self.tick  = 0
        self.balls = []
        for i, p in enumerate(profiles):
            r, c = BALL_POSITIONS[i % len(BALL_POSITIONS)]
            self.balls.append({"profile": p, "row": r, "col": c})
        # Fixed "new profile" ball always on map
        self.new_ball = {"profile": None, "row": 8, "col": 16, "is_new": True}

    def try_move(self, dr, dc):
        nr, nc = self.py + dr, self.px + dc
        dirs = {(-1,0):'up',(1,0):'down',(0,-1):'left',(0,1):'right'}
        self.direction = dirs.get((dr, dc), self.direction)
        all_balls = self.balls + [self.new_ball]
        for b in all_balls:
            if b["row"] == nr and b["col"] == nc:
                return False
        if walkable(nr, nc):
            self.py, self.px = nr, nc
            self.frame = (self.frame + 1) % 2
            return True
        return False

    def nearby_ball(self):
        all_balls = self.balls + [self.new_ball]
        for b in all_balls:
            if abs(b["row"] - self.py) <= 1 and abs(b["col"] - self.px) <= 1:
                return b
        return None

# ─── Rendering ────────────────────────────────────────────────────────────────

def render_map_panel(stdscr, gs, panel_y, panel_x, panel_h, panel_w):
    """Render the left game map panel."""
    map_h = panel_h - 2
    map_w = panel_w - 2

    cam_r = max(0, min(gs.py - map_h // 2, MAP_ROWS - map_h))
    cam_c = max(0, min(gs.px - map_w // 2, MAP_COLS - map_w))

    # Tiles
    for vr in range(map_h):
        for vc in range(map_w):
            mr, mc = cam_r + vr, cam_c + vc
            if 0 <= mr < MAP_ROWS and 0 <= mc < MAP_COLS:
                t = RAW_MAP[mr][mc]
                ch  = TILE_CHAR.get(t, ' ')
                col = TILE_COLOR.get(t, P_NORMAL)
                safe_add(stdscr, panel_y+1+vr, panel_x+1+vc, ch,
                         curses.color_pair(col))

    # Balls
    blink = (gs.tick // 6) % 2
    all_balls = gs.balls + [gs.new_ball]
    for b in all_balls:
        sr = b["row"] - cam_r
        sc = b["col"] - cam_c
        if 0 <= sr < map_h and 0 <= sc < map_w:
            if b.get("is_new"):
                ch = "➕" if blink else "✦"
                safe_add(stdscr, panel_y+1+sr, panel_x+1+sc, ch,
                         curses.color_pair(P_GREEN) | curses.A_BOLD)
            else:
                ch = BALL_GLYPHS[blink]
                safe_add(stdscr, panel_y+1+sr, panel_x+1+sc, ch,
                         curses.color_pair(P_BALL) | curses.A_BOLD)

    # Player sprite (3 wide rows shown as single chars to stay in bounds)
    # Use a compact 1-line sprite for the map cell
    pr = gs.py - cam_r
    pc = gs.px - cam_c
    if 0 <= pr < map_h and 0 <= pc < map_w:
        icons = {('down',0):'(◕‿◕)', ('down',1):'(◕ᴗ◕)',
                 ('up',0):'(⊙_⊙)',   ('up',1):'(⊙ω⊙)',
                 ('left',0):'(◑‿◑)', ('left',1):'(◑ᴗ◑)',
                 ('right',0):'(◐‿◐)','right,1)':'(◐ᴗ◐)'}
        icon = icons.get((gs.direction, gs.frame), '(◕‿◕)')
        # draw centered; 5 chars wide
        sc_draw = max(panel_x+1, panel_x+1 + pc - 2)
        safe_add(stdscr, panel_y+1+pr, sc_draw, icon,
                 curses.color_pair(P_PLAYER) | curses.A_BOLD)

    # Nearby ball hint
    ball = gs.nearby_ball()
    hint_attr = curses.color_pair(P_ORANGE) | curses.A_BOLD
    if ball:
        if ball.get("is_new"):
            hint = " ✦ New profile — press Space "
            safe_add(stdscr, panel_y + panel_h - 2, panel_x + 2, hint[:panel_w-4],
                     curses.color_pair(P_GREEN) | curses.A_BOLD)
        else:
            name = ball["profile"].get("name", "?")
            hint = f" ✦ {name} — press Space "
            safe_add(stdscr, panel_y + panel_h - 2, panel_x + 2, hint[:panel_w-4], hint_attr)

def render_status_panel(stdscr, gs, panel_y, panel_x, panel_h, panel_w):
    """Render right status panel."""
    attr = curses.color_pair(P_DIALOG)
    fill_rect(stdscr, panel_y+1, panel_x+1, panel_h-2, panel_w-2, ' ', attr)

    # ── Active config ──
    row = panel_y + 2
    safe_add(stdscr, row, panel_x+2, "── Active Config ──────────────",
             curses.color_pair(P_ORANGE) | curses.A_BOLD)
    row += 1

    cu = active_codex_url()
    cl = active_claude_url()
    cu_s = cu.replace("https://", "").replace("http://", "")[:panel_w-12] or "(none)"
    cl_s = cl.replace("https://", "").replace("http://", "")[:panel_w-12] or "(none)"

    safe_add(stdscr, row,   panel_x+2, "  🤖 Codex:", curses.color_pair(P_CODEX)  | curses.A_BOLD)
    safe_add(stdscr, row+1, panel_x+2, f"     {cu_s}", attr)
    safe_add(stdscr, row+2, panel_x+2, "  🧠 Claude:", curses.color_pair(P_CLAUDE) | curses.A_BOLD)
    safe_add(stdscr, row+3, panel_x+2, f"     {cl_s}", attr)
    row += 5

    # ── Profiles ──
    safe_add(stdscr, row, panel_x+2, "── Profiles ───────────────────",
             curses.color_pair(P_CYAN) | curses.A_BOLD)
    row += 1

    profiles = load_profiles()
    if not profiles:
        safe_add(stdscr, row, panel_x+2, "  (none)  press P to add",
                 curses.color_pair(P_DIM))
        row += 1
    else:
        for p in profiles[:6]:
            ca = "●" if (p.get("codex")  or {}).get("url") == cu and cu else "○"
            la = "●" if (p.get("claude") or {}).get("url") == cl and cl else "○"
            line = f"  🔮 {p['name']:<12} 🤖{ca} 🧠{la}"
            safe_add(stdscr, row, panel_x+2, line[:panel_w-4], attr)
            row += 1
        if len(profiles) > 6:
            safe_add(stdscr, row, panel_x+2,
                     f"  ... +{len(profiles)-6} more", curses.color_pair(P_DIM))
            row += 1

    row += 1
    # ── Nearby ball ──
    ball = gs.nearby_ball()
    if ball:
        safe_add(stdscr, row, panel_x+2, "── Nearby ─────────────────────",
                 curses.color_pair(P_GREEN) | curses.A_BOLD)
        row += 1
        if ball.get("is_new"):
            safe_add(stdscr, row, panel_x+2, "  ✦ New Profile",
                     curses.color_pair(P_GREEN) | curses.A_BOLD)
            row += 1
            safe_add(stdscr, row, panel_x+2, "  Press Space to add",
                     curses.color_pair(P_DIM))
        else:
            name = ball["profile"].get("name", "?")
            safe_add(stdscr, row, panel_x+2, f"  🔮 {name}", attr | curses.A_BOLD)
            row += 1
            cfg_c = (ball["profile"].get("codex")  or {})
            cfg_l = (ball["profile"].get("claude") or {})
            if cfg_c.get("url"):
                safe_add(stdscr, row, panel_x+4, f"🤖 {cfg_c['url'][:panel_w-10].replace('https://','')}", curses.color_pair(P_CODEX))
                row += 1
            if cfg_l.get("url"):
                safe_add(stdscr, row, panel_x+4, f"🧠 {cfg_l['url'][:panel_w-10].replace('https://','')}", curses.color_pair(P_CLAUDE))
                row += 1

def render_hud(stdscr, h, w):
    """Top title bar + bottom key hints."""
    title = " ✦ Agent Launcher ✦ "
    safe_add(stdscr, 0, (w - len(title)) // 2, title,
             curses.color_pair(P_ORANGE) | curses.A_BOLD)

    hints = [
        ("WASD/↑↓←→", "move"),
        ("Space", "interact"),
        ("P", "profiles"),
        ("Q", "quit"),
    ]
    bar = "  "
    for key, desc in hints:
        bar += f" [{key}] {desc} "
    safe_add(stdscr, h-1, 0, bar[:w-1].ljust(w-1),
             curses.color_pair(P_STATUSBAR))

# ─── Interaction ──────────────────────────────────────────────────────────────

def interact_with_ball(stdscr, ball):
    profile = ball["profile"]
    name    = profile.get("name", "?")

    codex_cfg  = profile.get("codex")  or {}
    claude_cfg = profile.get("claude") or {}
    has_codex  = bool(codex_cfg.get("url") and codex_cfg.get("key"))
    has_claude = bool(claude_cfg.get("url") and claude_cfg.get("key"))

    dialog_box(stdscr, [
        f"  🔮 A profile appeared!",
        f"  » {name} «",
        "  What will you do?",
    ])

    options = []
    if has_codex:  options.append("🤖 Launch Codex")
    if has_claude: options.append("🧠 Launch Claude")
    options += ["✏  Edit profile", "✕  Cancel"]

    choice = choice_dialog(stdscr, f"🔮 {name}", options)
    if choice == -1 or options[choice] == "✕  Cancel":
        return None, None

    if options[choice] == "✏  Edit profile":
        return "edit", ball

    agent = "codex" if "Codex" in options[choice] else "claude"
    if agent == "codex":
        apply_codex(codex_cfg["url"], codex_cfg["key"])
        launch_animation(stdscr, "Codex", name)
        return CODEX_BIN, []
    else:
        apply_claude(claude_cfg["url"], claude_cfg["key"])
        launch_animation(stdscr, "Claude", name)
        return CLAUDE_BIN, []

# ─── Main loop ────────────────────────────────────────────────────────────────

def game_loop(stdscr):
    init_colors()
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(80)

    profiles = load_profiles()
    gs = GameState(profiles)

    if not profiles:
        stdscr.nodelay(False)
        stdscr.timeout(-1)
        dialog_box(stdscr, [
            "  No profiles yet!",
            "  Press P to add your first profile.",
            "  Then walk up to a 🔮 to launch!",
        ])
        stdscr.nodelay(True)
        stdscr.timeout(80)

    while True:
        h, w = stdscr.getmaxyx()

        # Layout: left map (2/3), right panel (1/3)
        map_w   = max(20, (w * 2) // 3)
        panel_w = max(20, w - map_w)
        map_h   = h - 2   # top title + bottom bar

        stdscr.erase()

        # Draw panels
        draw_border(stdscr, 1, 0, map_h, map_w, P_ORANGE, "✦ World ✦")
        draw_border(stdscr, 1, map_w, map_h, panel_w, P_CYAN, "✦ Status ✦")

        render_map_panel(stdscr, gs, 1, 0, map_h, map_w)
        render_status_panel(stdscr, gs, 1, map_w, map_h, panel_w)
        render_hud(stdscr, h, w)

        stdscr.refresh()
        gs.tick += 1

        k = stdscr.getch()
        if k == -1:
            continue

        if k in (ord('q'), ord('Q')):
            return None, None

        elif k in (ord('p'), ord('P')):
            stdscr.nodelay(False); stdscr.timeout(-1)
            manage_profiles_screen(stdscr)
            profiles = load_profiles()
            gs = GameState(profiles)
            stdscr.nodelay(True); stdscr.timeout(80)

        elif k in (curses.KEY_UP,    ord('w'), ord('W')): gs.try_move(-1,  0)
        elif k in (curses.KEY_DOWN,  ord('s'), ord('S')): gs.try_move( 1,  0)
        elif k in (curses.KEY_LEFT,  ord('a'), ord('A')): gs.try_move( 0, -1)
        elif k in (curses.KEY_RIGHT, ord('d'), ord('D')): gs.try_move( 0,  1)

        elif k in (ord(' '), 10, 13):
            ball = gs.nearby_ball()
            if ball:
                stdscr.nodelay(False); stdscr.timeout(-1)
                if ball.get("is_new"):
                    # New profile ball
                    dialog_box(stdscr, [
                        "  ✦ Add a new profile!",
                        "  Configure a relay station",
                        "  for Codex or Claude.",
                    ])
                    result = edit_profile_screen(stdscr, {})
                    if result:
                        profiles = load_profiles()
                        profiles.append(result)
                        save_profiles(profiles)
                        gs = GameState(load_profiles())
                        dialog_box(stdscr, [
                            f"  ✦ Profile saved!",
                            f"  » {result['name']} «",
                            "  Walk up to it to launch!",
                        ])
                    stdscr.nodelay(True); stdscr.timeout(80)
                else:
                    result, extra = interact_with_ball(stdscr, ball)
                    if result == "edit":
                        updated = edit_profile_screen(stdscr, extra["profile"])
                        if updated:
                            profiles = load_profiles()
                            for i, p in enumerate(profiles):
                                if p["name"] == extra["profile"]["name"]:
                                    profiles[i] = updated
                                    break
                            save_profiles(profiles)
                            gs = GameState(load_profiles())
                    elif result:
                        return result, extra
                    stdscr.nodelay(True); stdscr.timeout(80)
                stdscr.nodelay(True); stdscr.timeout(80)

# ─── Entry ────────────────────────────────────────────────────────────────────

def main():
    result = curses.wrapper(game_loop)
    bin_, args = result if result else (None, None)
    if bin_ and isinstance(bin_, str) and os.path.exists(bin_):
        os.execv(bin_, [bin_] + (args or []) + sys.argv[1:])
    elif bin_:
        print(f"Binary not found: {bin_}")
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
