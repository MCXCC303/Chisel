"""帮助文档页面."""

from __future__ import annotations

import time
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Markdown

HELP_SECTIONS: dict[str, str] = {}


HELP_FILE_MAP = {
    "概述": "01-overview.md",
    "工作原理": "02-how-it-works.md",
    "打包 (Pack)": "03-pack.md",
    "解包 (Unpack)": "04-unpack.md",
    "预览 (Preview)": "05-preview.md",
    "清除无效记录": "06-clean.md",
    "常见问题": "07-faq.md",
    "声明": "08-disclaims.md",
}


def _load_help_sections() -> dict[str, str]:
    help_dir = Path(__file__).parent.parent / "help"
    sections: dict[str, str] = {}
    for title, filename in HELP_FILE_MAP.items():
        file_path = help_dir / filename
        if file_path.exists():
            sections[title] = file_path.read_text(encoding="utf-8").strip()
        else:
            sections[title] = f"# {title}\n\n帮助文档未找到。"
    return sections


class HelpScreen(Screen):
    """程序帮助文档 — 左侧标题列表 + 右侧 Markdown 渲染."""

    _last_select_ts: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="help-container"):
            yield Label("Chisel 帮助文档", classes="title")
            with Horizontal(id="help-panels"):
                with VerticalScroll(id="help-nav"):
                    yield ListView(
                        ListItem(Label("概述")),
                        ListItem(Label("工作原理")),
                        ListItem(Label("打包 (Pack)")),
                        ListItem(Label("解包 (Unpack)")),
                        ListItem(Label("清除无效记录")),
                        ListItem(Label("预览 (Preview)")),
                        ListItem(Label("常见问题")),
                        ListItem(Label("声明")),
                        id="help-list",
                    )
                with VerticalScroll(id="help-content"):
                    yield Markdown("加载中...", id="help-md")
            with Horizontal(classes="btn-row"):
                yield Button("返回", variant="primary", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        global HELP_SECTIONS
        if not HELP_SECTIONS:
            HELP_SECTIONS = _load_help_sections()
        self.query_one("#help-md", Markdown).update(HELP_SECTIONS.get("概述", ""))
        self.query_one("#help-list", ListView).index = 0

    @on(ListView.Highlighted, "#help-list")
    def on_section_change(self, event: ListView.Highlighted) -> None:
        if event.item is not None:
            label = event.item.query_one(Label).render()
            title = label.plain if hasattr(label, 'plain') else str(label)
            if title in HELP_SECTIONS:
                self.query_one("#help-md", Markdown).update(HELP_SECTIONS[title])

    @on(ListView.Selected, "#help-list")
    def _on_list_select(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        label = event.item.query_one(Label).render()
        title = label.plain if hasattr(label, 'plain') else str(label)
        if title != "声明":
            return
        now = time.monotonic()
        if now - self._last_select_ts < 0.5:
            self._last_select_ts = 0
            from .auth_ui import UnlockScreen
            self.app.push_screen(UnlockScreen())
        else:
            self._last_select_ts = now

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.app.pop_screen()
