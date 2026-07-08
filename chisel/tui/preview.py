"""会话预览页面."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from ..models import ProjectEntry, SessionEntry
from .helpers import (
    escape_markup, format_size, parse_session_jsonl, softwrap,
    strip_orphan_closing_tags,
)


class SessionPreviewScreen(Screen):
    """预览会话内容，底部起始 + 分批加载."""

    CHUNK_SIZE = 30
    MAX_LINES = 5000

    def __init__(self, uuid: str, proj: ProjectEntry, sess: SessionEntry) -> None:
        super().__init__()
        self._uuid = uuid
        self._proj = proj
        self._sess = sess
        self._all_messages: list[dict] = []
        self._shown_count = 0
        self._wrap_width = 300
        self._rendered_content = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="preview-container"):
            yield Label(
                f"预览: {Path(self._proj.original_path).name} / {self._uuid}",
                id="preview-title", classes="title",
            )
            with VerticalScroll(id="preview-scroll"):
                yield Static("正在加载...", id="preview-content")
            with Horizontal(classes="btn-row"):
                yield Button("返回", variant="warning", id="btn-back")
                yield Button("加载更多 ↑", variant="default", id="btn-more")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        self._all_messages = parse_session_jsonl(self._sess.jsonl_path)
        if not self._all_messages:
            self.query_one("#preview-content", Static).update("[dim]该会话无消息内容[/dim]")
            return
        self._wrap_width = 300
        self._show_next_chunk()
        self.call_after_refresh(self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        try:
            self.query_one("#preview-scroll", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def _show_next_chunk(self) -> None:
        total = len(self._all_messages)
        end = total - self._shown_count
        start = max(0, end - self.CHUNK_SIZE)
        chunk = self._all_messages[start:end]
        if not chunk:
            return

        new_lines = self._render_messages(chunk)
        self._shown_count += len(chunk)

        scroll = self.query_one("#preview-scroll", VerticalScroll)
        old_scroll = scroll.scroll_offset.y
        old_max = scroll.max_scroll_y

        preview = self.query_one("#preview-content", Static)
        if self._rendered_content:
            combined = "\n".join(new_lines) + "\n" + self._rendered_content
        else:
            combined = "\n".join(new_lines)

        all_lines = combined.split("\n")
        if len(all_lines) > self.MAX_LINES:
            kept = all_lines[-self.MAX_LINES:]
            while kept and not kept[0].strip():
                kept.pop(0)
            if kept:
                kept[0] = strip_orphan_closing_tags(kept[0])
            combined = "\n".join(kept)
        self._rendered_content = combined
        preview.update(combined)

        self.call_after_refresh(
            lambda: self._restore_scroll(scroll, old_scroll, old_max)
        )

        remaining = total - self._shown_count
        btn = self.query_one("#btn-more", Button)
        if remaining > 0:
            btn.label = f"加载更多 ↑ ({remaining})"
            btn.display = True
        else:
            btn.display = False

    def _restore_scroll(self, scroll: VerticalScroll, old_scroll: int, old_max: int) -> None:
        try:
            new_max = scroll.max_scroll_y
            scroll.scroll_to(y=old_scroll + (new_max - old_max), animate=False)
        except Exception:
            pass

    def _render_messages(self, messages: list[dict]) -> list[str]:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            ts = msg.get("timestamp", "")
            if ts:
                try:
                    ts = datetime.fromtimestamp(ts / 1000).strftime("%m-%d %H:%M")
                except Exception:
                    pass

            if role == "user":
                for uline in softwrap(msg.get("text", ""), self._wrap_width):
                    lines.append(f"[bold #4fc3f7]┃[/bold #4fc3f7] [bold #e0e0e0]{escape_markup(uline)}[/bold #e0e0e0]")
                if ts:
                    lines.append(f"[bold #4fc3f7]┃[/bold #4fc3f7] [dim #666666]{ts}[/dim #666666]")
                lines.append("")

            elif role == "assistant":
                has_text = any(p.get("type") == "text" for p in msg.get("parts", []))
                for part in msg.get("parts", []):
                    pt = part.get("type", "")
                    if pt == "text":
                        for tline in softwrap(part.get("text", ""), self._wrap_width):
                            lines.append(f"[bold #ce93d8]┃[/bold #ce93d8] [#b0b0b0]{escape_markup(tline)}[/#b0b0b0]")
                    elif pt == "thinking":
                        lines.append(f"[dim italic #888888]  Thought: {escape_markup(part.get('thinking', ''))}[/dim italic #888888]")
                    elif pt == "tool_use":
                        lines.extend(self._render_tool(part))
                if ts:
                    if has_text:
                        lines.append(f"[bold #ce93d8]┃[/bold #ce93d8] [dim #555555]{ts}[/dim #555555]")
                    else:
                        lines.append(f"[dim #555555]  {ts}[/dim #555555]")
                lines.append("")
        return lines

    def _render_tool(self, part: dict) -> list[str]:
        name = part.get("name", "?")
        inp = part.get("input", {}) or {}
        lines: list[str] = []
        w = self._wrap_width

        if name in ("Write", "Edit", "Update"):
            file_path = str(inp.get("file_path", "?"))
            lines.append(f"[#81c784]  ┌─ {escape_markup(name)}: {escape_markup(file_path)}[/#81c784]")
            if name == "Edit":
                shown = 0
                for l in str(inp.get("old_string", "")).split("\n"):
                    for wl in softwrap(l, w - 6):
                        if shown >= 5:
                            break
                        lines.append(f"[#81c784]  │[/#81c784] [dim #ff8a80]- {escape_markup(wl)}[/dim #ff8a80]")
                        shown += 1
                for l in str(inp.get("new_string", "")).split("\n"):
                    for wl in softwrap(l, w - 6):
                        if shown >= 10:
                            break
                        lines.append(f"[#81c784]  │[/#81c784] [dim #a5d6a7]+ {escape_markup(wl)}[/dim #a5d6a7]")
                        shown += 1
                if shown >= 10:
                    lines.append(f"[#81c784]  │[/#81c784] [dim #666666]  ...[/dim #666666]")
            else:
                shown = 0
                for cl in str(inp.get("content", "")).split("\n"):
                    for wl in softwrap(cl, w - 4):
                        if shown >= 8:
                            break
                        lines.append(f"[#81c784]  │[/#81c784] [dim #888888]{escape_markup(wl)}[/dim #888888]")
                        shown += 1
                    if shown >= 8:
                        break
                if shown >= 8:
                    lines.append(f"[#81c784]  │[/#81c784] [dim #666666]  ...[/dim #666666]")
            lines.append(f"[#81c784]  └─[/#81c784]")

        elif name == "Bash":
            cmd = str(inp.get("command", "")) or "?"
            cmd_lines = cmd.split("\n")
            first = cmd_lines[0]
            lines.append(f"[#81c784]  ┌─ $ {escape_markup(first)[:w - 6]}[/#81c784]")
            shown = 0
            for cl in cmd_lines[1:]:
                for wl in softwrap(cl, w - 4):
                    if shown >= 8:
                        break
                    lines.append(f"[#81c784]  │[/#81c784] [dim #888888]{escape_markup(wl)}[/dim #888888]")
                    shown += 1
                if shown >= 8:
                    break
            if shown >= 8:
                lines.append(f"[#81c784]  │[/#81c784] [dim #666666]  ...[/dim #666666]")
            lines.append(f"[#81c784]  └─[/#81c784]")

        elif name == "ExitPlanMode":
            plan = str(inp.get("plan", ""))
            file_path = str(inp.get("planFilePath", "?"))
            lines.append(f"[#81c784]  ┌─ ExitPlanMode: {escape_markup(file_path)}[/#81c784]")
            for pl in plan.split("\n"):
                for wl in softwrap(pl, w - 4):
                    lines.append(f"[#81c784]  │[/#81c784] [dim #888888]{escape_markup(wl)}[/dim #888888]")
            lines.append(f"[#81c784]  └─[/#81c784]")

        elif name == "Read":
            file_path = str(inp.get("file_path", "?"))
            offset = inp.get("offset")
            limit = inp.get("limit")
            if offset is not None and limit is not None:
                lines.append(f"[#81c784]  ⚙ Read[/#81c784] [#b0b0b0]{escape_markup(file_path)}[/#b0b0b0] [dim #666666]{offset}-{offset + limit}[/dim #666666]")
            else:
                lines.append(f"[#81c784]  ⚙ Read[/#81c784] [#b0b0b0]{escape_markup(file_path)}[/#b0b0b0]")

        elif name == "Agent":
            desc = str(inp.get("description", ""))
            sub = str(inp.get("subagent_type", ""))
            prefix = sub if sub else "Agent"
            lines.append(f"[#81c784]  ⚙ {escape_markup(prefix)}[/#81c784] [dim #b0b0b0]{escape_markup(desc)[:w - 4]}[/dim #b0b0b0]")

        else:
            inp_str = str(inp)
            lines.append(f"[#81c784]  ⚙ {escape_markup(name)}[/#81c784] [dim #666666]{escape_markup(inp_str)[:w - 4]}[/dim #666666]")

        return lines

    @on(Button.Pressed, "#btn-more")
    def on_more(self) -> None:
        self._show_next_chunk()

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.app.pop_screen()
