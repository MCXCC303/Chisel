"""TUI 辅助函数."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from textual.app import App

from ..models import ClaudeData, ProjectEntry


def open_file_dialog(directory: bool = False, save: bool = False) -> str | None:
    """调用系统原生文件选择器。按优先级尝试: zenity, kdialog."""
    if shutil.which("zenity"):
        try:
            if save:
                result = subprocess.run(
                    ["zenity", "--file-selection", "--save", "--confirm-overwrite"],
                    capture_output=True, text=True, timeout=60,
                )
            elif directory:
                result = subprocess.run(
                    ["zenity", "--file-selection", "--directory"],
                    capture_output=True, text=True, timeout=60,
                )
            else:
                result = subprocess.run(
                    ["zenity", "--file-selection"],
                    capture_output=True, text=True, timeout=60,
                )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    if shutil.which("kdialog"):
        try:
            if directory:
                result = subprocess.run(
                    ["kdialog", "--getexistingdirectory", str(Path.home())],
                    capture_output=True, text=True, timeout=60,
                )
            elif save:
                result = subprocess.run(
                    ["kdialog", "--getsavefilename", str(Path.home())],
                    capture_output=True, text=True, timeout=60,
                )
            else:
                result = subprocess.run(
                    ["kdialog", "--getopenfilename", str(Path.home())],
                    capture_output=True, text=True, timeout=60,
                )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    return None


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def estimate_project_size(claude_dir: Path, proj: ProjectEntry) -> int:
    total = 0
    for s in proj.sessions:
        if s.jsonl_path and s.jsonl_path.exists():
            total += s.jsonl_path.stat().st_size
        if s.has_file_history:
            fh_dir = claude_dir / "file-history" / s.uuid
            if fh_dir.exists():
                for f in fh_dir.rglob("*"):
                    if f.is_file():
                        total += f.stat().st_size
        if s.has_tasks:
            t_dir = claude_dir / "tasks" / s.uuid
            if t_dir.exists():
                for f in t_dir.rglob("*"):
                    if f.is_file():
                        total += f.stat().st_size
    return total


def get_session_summaries(proj: ProjectEntry) -> dict[str, str]:
    summaries: dict[str, str] = {}
    latest_per_session: dict[str, dict] = {}
    for entry in proj.history_entries:
        sid = entry.get("sessionId", "")
        if sid and (
            sid not in latest_per_session
            or entry.get("timestamp", 0) > latest_per_session[sid].get("timestamp", 0)
        ):
            latest_per_session[sid] = entry
    for sid, entry in latest_per_session.items():
        display = entry.get("display", "")
        first_line = display.split("\n")[0][:60]
        summaries[sid] = first_line
    return summaries


def count_jsonl_lines(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    count = 0
    with open(path, "rb") as f:
        for _ in f:
            count += 1
    return count


def timestamp_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def has_special_chars(path: str) -> bool:
    """检查路径是否含中文或特殊字符（可能导致编码碰撞）."""
    for ch in path:
        code = ord(ch)
        if code > 127:  # 非 ASCII
            return True
    return False


def default_target_path(original_path: str, basename: str) -> str:
    if not original_path:
        return f"/home/{os.getlogin()}/projects/{basename}"
    parts = original_path.split("/")
    if len(parts) >= 3 and parts[1] == "home":
        parts[2] = os.getlogin()
        return "/".join(parts)
    return original_path


def resolve_target_dir(selected: str) -> tuple[str, str]:
    p = Path(selected).resolve()
    if p.name == ".claude":
        return str(p), str(p.parent / ".claude.json")
    return str(p / ".claude"), str(p / ".claude.json")


def navigate_home(app: App) -> None:
    for _ in range(50):
        try:
            app.pop_screen()
        except Exception:
            break
    from .start import StartScreen  # noqa: F811
    app.push_screen(StartScreen())


def escape_markup(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


def strip_orphan_closing_tags(text: str) -> str:
    while True:
        m = re.match(r"\s*\[/[^\]]*\]", text)
        if not m:
            break
        text = text[m.end():]
    return text


def display_width(text: str) -> int:
    w = 0
    for ch in text:
        ea = unicodedata.east_asian_width(ch)
        w += 2 if ea in ("F", "W") else 1
    return w


def softwrap(text: str, width: int = 70) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        while display_width(paragraph) > width:
            cut = 0
            w = 0
            best_cut = 0
            for i, ch in enumerate(paragraph):
                ea = unicodedata.east_asian_width(ch)
                w += 2 if ea in ("F", "W") else 1
                if w > width:
                    break
                cut = i + 1
                if ch == " ":
                    best_cut = i + 1
            final_cut = best_cut if best_cut > width // 4 else cut
            if final_cut == 0:
                final_cut = max(1, len(paragraph) // 2)
            lines.append(paragraph[:final_cut].rstrip())
            paragraph = paragraph[final_cut:].lstrip()
        if paragraph:
            lines.append(paragraph)
    return lines


def parse_session_jsonl(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    messages: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = msg.get("type", "")
            message = msg.get("message", {})
            timestamp = msg.get("timestamp", "")
            if t == "user":
                content = message.get("content", "")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            break
                if text.strip():
                    messages.append({"role": "user", "text": text, "timestamp": timestamp})
            elif t == "assistant":
                content = message.get("content", "")
                parts = []
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        pt = part.get("type", "")
                        if pt == "text":
                            parts.append({"type": "text", "text": part.get("text", "")})
                        elif pt == "thinking":
                            parts.append({"type": "thinking", "thinking": part.get("thinking", "")})
                        elif pt == "tool_use":
                            parts.append({"type": "tool_use", "name": part.get("name", "?"),
                                          "input": part.get("input", {})})
                if parts:
                    messages.append({"role": "assistant", "parts": parts, "timestamp": timestamp})
    return messages
