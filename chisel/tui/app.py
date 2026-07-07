"""Chisel 主应用."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from .start import StartScreen

_CSS_DIR = Path(__file__).parent / "css"
_CSS_FILES = [
    "base.css",
    "start.css",
    "pack.css",
    "unpack.css",
    "preview.css",
    "help.css",
    "about.css",
    "message.css",
]


def _load_css() -> str:
    parts: list[str] = []
    for fname in _CSS_FILES:
        p = _CSS_DIR / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


class ChiselApp(App):
    """Chisel - Claude Code 历史记录迁移工具."""

    CSS = _load_css()

    BINDINGS = [
        Binding("ctrl+c", "quit", "退出", priority=True),
    ]

    def on_mount(self) -> None:
        self.push_screen(StartScreen())
