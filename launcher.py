#!/usr/bin/env python3
"""
codex-launcher: A TUI launcher for Codex CLI that manages relay station profiles
and switches between them before launching Codex.
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

CODEX_DIR = Path.home() / ".codex"
CONFIG_FILE = CODEX_DIR / "config.toml"
AUTH_FILE = CODEX_DIR / "auth.json"
RELAY_PROFILES = CODEX_DIR / "relay-profiles.json"
BACKUP_DIR = CODEX_DIR / ".auth-backups"

CODEX_BIN = (
    shutil.which("codex")
    or str(Path.home() / "Applications/Codex.app/Contents/Resources/codex")
    or "/Applications/Codex.app/Contents/Resources/codex"
)

# ─── Data layer ───────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)

def load_profiles():
    return load_json(RELAY_PROFILES, [])

def detect_current_url():
    try:
        text = CONFIG_FILE.read_text()
        m = re.search(r'^base_url\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else ""
    except Exception:
        return ""

def detect_current_name():
    url = detect_current_url()
    for p in load_profiles():
        if p["url"] == url:
            return p["name"]
    return url or "unknown"

def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if CONFIG_FILE.exists():
        shutil.copy(CONFIG_FILE, BACKUP_DIR / f"config.toml.{ts}")
    if AUTH_FILE.exists():
        shutil.copy(AUTH_FILE, BACKUP_DIR / f"auth.json.{ts}")

def apply_relay(url: str, key: str):
    backup()
    text = CONFIG_FILE.read_text()
    text = re.sub(r'^base_url\s*=.*', f'base_url = "{url}"', text, flags=re.MULTILINE)
    text = re.sub(r'^preferred_auth_method\s*=.*', 'preferred_auth_method = "apikey"', text, flags=re.MULTILINE)
    text = re.sub(r'^model_provider\s*=.*', 'model_provider = "custom"', text, flags=re.MULTILINE)
    CONFIG_FILE.write_text(text)
    save_json(AUTH_FILE, {"auth_mode": "apikey", "OPENAI_API_KEY": key})

def save_profile(name: str, url: str, key: str):
    profiles = load_profiles()
    for p in profiles:
        if p["name"] == name:
            p["url"] = url
            p["key"] = key
            break
    else:
        profiles.append({"name": name, "url": url, "key": key})
    save_json(RELAY_PROFILES, profiles)

def delete_profile(idx: int):
    profiles = load_profiles()
    if 0 <= idx < len(profiles):
        profiles.pop(idx)
        save_json(RELAY_PROFILES, profiles)

# ─── TUI components ───────────────────────────────────────────────────────────

C_SELECTED = 1
C_HEADER   = 2
C_STATUS   = 3
C_DIM      = 4
C_SUCCESS  = 5
C_DELETE   = 6

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_HEADER,   curses.COLOR_CYAN,  -1)
    curses.init_pair(C_STATUS,   curses.COLOR_YELLOW,-1)
    curses.init_pair(C_DIM,      8,                  -1)
    curses.init_pair(C_SUCCESS,  curses.COLOR_GREEN, -1)
    curses.init_pair(C_DELETE,   curses.COLOR_RED,   -1)

def draw_box(win, y, x, h, w, title=""):
    try:
        win.attron(curses.color_pair(C_DIM))
        win.addch(y, x, curses.ACS_ULCORNER)
        win.addch(y, x+w-1, curses.ACS_URCORNER)
        win.addch(y+h-1, x, curses.ACS_LLCORNER)
        win.addch(y+h-1, x+w-1, curses.ACS_LRCORNER)
        for i in range(1, w-1):
            win.addch(y, x+i, curses.ACS_HLINE)
            win.addch(y+h-1, x+i, curses.ACS_HLINE)
        for i in range(1, h-1):
            win.addch(y+i, x, curses.ACS_VLINE)
            win.addch(y+i, x+w-1, curses.ACS_VLINE)
        win.attroff(curses.color_pair(C_DIM))
        if title:
            win.attron(curses.color_pair(C_HEADER) | curses.A_BOLD)
            win.addstr(y, x+2, f" {title} ")
            win.attroff(curses.color_pair(C_HEADER) | curses.A_BOLD)
    except curses.error:
        pass

def safe_addstr(win, y, x, text, attr=0):
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        text = text[:w - x - 1]
        if text:
            win.addstr(y, x, text, attr)
    except curses.error:
        pass

def menu(stdscr, title: str, items: list, subtitle: str = "",
         delete_indices: set = None) -> int:
    """
    Generic menu. Returns selected index, -1 for cancel.
    Press 'd' on a deletable item to return -(idx+100).
    """
    curses.curs_set(0)
    idx = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        box_h = min(len(items) + 6, h - 2)
        box_w = min(max(len(title)+6, max((len(s) for s in items), default=20)+8, 44), w-4)
        by = max(0, (h - box_h) // 2)
        bx = max(0, (w - box_w) // 2)

        draw_box(stdscr, by, bx, box_h, box_w, title)

        if subtitle:
            safe_addstr(stdscr, by+1, bx+2, subtitle[:box_w-4], curses.color_pair(C_STATUS))

        offset = 1 if subtitle else 0
        visible_start = max(0, idx - (box_h - 6 - offset))
        for i, item in enumerate(items[visible_start:visible_start+box_h-4-offset], visible_start):
            row = by + 2 + offset + (i - visible_start)
            if row >= by + box_h - 1:
                break
            is_deletable = delete_indices and i in delete_indices
            if i == idx:
                safe_addstr(stdscr, row, bx+1, " "*(box_w-2), curses.color_pair(C_SELECTED))
                safe_addstr(stdscr, row, bx+3, item[:box_w-8], curses.color_pair(C_SELECTED)|curses.A_BOLD)
                if is_deletable:
                    safe_addstr(stdscr, row, bx+box_w-6, "[d:del]",
                                curses.color_pair(C_DELETE)|curses.A_BOLD)
            else:
                safe_addstr(stdscr, row, bx+3, item[:box_w-6])

        hint = "↑↓ move  Enter select  q/Esc cancel" + ("  d delete" if delete_indices else "")
        safe_addstr(stdscr, by+box_h-1, bx+2, hint[:box_w-4], curses.color_pair(C_DIM))
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord('k')):
            idx = (idx - 1) % len(items)
        elif key in (curses.KEY_DOWN, ord('j')):
            idx = (idx + 1) % len(items)
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return idx
        elif key in (ord('q'), ord('Q'), 27):
            return -1
        elif key == ord('d') and delete_indices and idx in delete_indices:
            return -(idx + 100)

def input_box(stdscr, prompt: str, default: str = "", secret: bool = False) -> str:
    curses.curs_set(1)
    h, w = stdscr.getmaxyx()
    box_w = min(64, w - 4)
    bx = (w - box_w) // 2
    by = h // 2 - 2

    draw_box(stdscr, by, bx, 5, box_w, "Input")
    safe_addstr(stdscr, by+1, bx+2, prompt[:box_w-4], curses.color_pair(C_STATUS))

    value = list(default)
    while True:
        display = ("*" * len(value)) if secret else "".join(value)
        safe_addstr(stdscr, by+2, bx+2, " " * (box_w-4))
        safe_addstr(stdscr, by+2, bx+2, display[:box_w-4])
        safe_addstr(stdscr, by+3, bx+2, "Enter confirm  Esc cancel"[:box_w-4], curses.color_pair(C_DIM))
        stdscr.move(by+2, bx+2+min(len(display), box_w-5))
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            curses.curs_set(0)
            return "".join(value)
        elif key == 27:
            curses.curs_set(0)
            return ""
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if value:
                value.pop()
        elif 32 <= key <= 126:
            value.append(chr(key))

def flash(stdscr, msg: str, color_pair: int, duration: float = 1.0):
    h, w = stdscr.getmaxyx()
    x = max(0, (w - len(msg) - 4) // 2)
    try:
        stdscr.addstr(h//2, x, f"  {msg}  ", curses.color_pair(color_pair)|curses.A_BOLD)
        stdscr.refresh()
        time.sleep(duration)
    except curses.error:
        pass

def confirm(stdscr, msg: str) -> bool:
    choice = menu(stdscr, "Confirm", [msg, "Cancel"])
    return choice == 0

# ─── Screens ──────────────────────────────────────────────────────────────────

def screen_relay(stdscr) -> bool:
    while True:
        profiles = load_profiles()
        current_url = detect_current_url()
        items = []
        for p in profiles:
            active = " ●" if p["url"] == current_url else ""
            items.append(f"{p['name']}{active}  {p['url']}  ({p['key'][:8]}...)")
        items.append("+ Add new relay")

        delete_indices = set(range(len(profiles)))
        choice = menu(stdscr, "Select Relay", items,
                      f"Active: {detect_current_name()}", delete_indices)

        if choice == -1:
            return False

        # Delete
        if choice <= -100:
            real_idx = abs(choice) - 100
            p = profiles[real_idx]
            stdscr.erase()
            if confirm(stdscr, f"Delete {p['name']} ?"):
                delete_profile(real_idx)
                flash(stdscr, f"Deleted: {p['name']}", C_DELETE, 0.7)
            continue

        # Add new
        if choice == len(profiles):
            stdscr.erase()
            url = input_box(stdscr, f"URL [{current_url}]:", current_url)
            if not url:
                continue
            stdscr.erase()
            key = input_box(stdscr, "API Key:", secret=True)
            if not key:
                continue
            stdscr.erase()
            name = input_box(stdscr, "Save as name (Enter to skip):")
            if name:
                save_profile(name, url, key)
            apply_relay(url, key)
            flash(stdscr, f"Switched: {name or url}", C_SUCCESS)
            return True

        # Select existing
        p = profiles[choice]
        apply_relay(p["url"], p["key"])
        flash(stdscr, f"Switched: {p['name']}", C_SUCCESS)
        return True

def main_tui(stdscr):
    init_colors()
    curses.curs_set(0)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = "Codex Launcher"
        safe_addstr(stdscr, 1, (w-len(title))//2, title,
                    curses.color_pair(C_HEADER)|curses.A_BOLD)
        cur = f"Active relay: {detect_current_name()}"
        safe_addstr(stdscr, 2, (w-len(cur))//2, cur, curses.color_pair(C_STATUS))

        choice = menu(stdscr, "Main Menu", [
            "▶  Launch Codex",
            "⇄  Switch relay",
            "✕  Quit",
        ])

        if choice == -1 or choice == 2:
            return None
        elif choice == 0:
            return "launch"
        elif choice == 1:
            screen_relay(stdscr)

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    action = curses.wrapper(main_tui)
    if action == "launch":
        if not os.path.exists(CODEX_BIN):
            print(f"codex not found: {CODEX_BIN}")
            sys.exit(1)
        os.execv(CODEX_BIN, [CODEX_BIN] + sys.argv[1:])
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
