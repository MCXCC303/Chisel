"""打包流程页面."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input,
    Label, ProgressBar, Static,
)

from ..models import ClaudeData, ProjectEntry
from ..packer import pack
from ..scanner import scan
from .helpers import (
    count_jsonl_lines, estimate_project_size, format_size,
    get_session_summaries, navigate_home, open_file_dialog, timestamp_str,
)
from .message import MessageScreen
from .preview import SessionPreviewScreen


# ═══════════════════════════════════════════════
# Scan Screen
# ═══════════════════════════════════════════════

class ScanScreen(Screen):
    """扫描并选择要打包的项目 — 表格视图，支持列排序."""

    BINDINGS = [
        Binding("space", "toggle_row", "选择/取消"),
    ]

    scan_data: ClaudeData | None = None
    _sort_col: str = "project"
    _sort_asc: bool = True
    _selected: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="scan-container"):
            yield Label("选择要打包的项目", classes="title")
            yield Label("正在扫描 ~/.claude/ ...", id="scan-status", classes="subtitle")
            yield ProgressBar(id="scan-progress", total=100)
            with VerticalScroll(id="list-container"):
                yield DataTable(id="project-table", cursor_type="row")
            with Horizontal(classes="btn-row"):
                yield Button("全选", variant="default", id="btn-all")
                yield Button("取消全选", variant="default", id="btn-none")
                yield Button("返回主页", variant="default", id="btn-home")
                yield Button("确认 →", variant="primary", id="btn-confirm")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._do_scan(), exclusive=True)

    async def _do_scan(self) -> None:
        status = self.query_one("#scan-status", Label)
        progress = self.query_one("#scan-progress", ProgressBar)
        table = self.query_one("#project-table", DataTable)

        status.update("正在读取 ~/.claude.json ...")
        progress.advance(30)
        claude_dir = Path.home() / ".claude"
        claude_json = Path.home() / ".claude.json"
        status.update("正在扫描项目目录 ...")
        self.scan_data = scan(claude_dir=claude_dir, claude_json_path=claude_json)
        progress.advance(60)
        status.update(f"发现 {len(self.scan_data.projects)} 个项目")
        progress.advance(10)

        table.add_column("", width=3, key="check")
        table.add_column("项目", key="project")
        table.add_column("会话", key="sessions", width=8)
        table.add_column("历史", key="history", width=8)
        table.add_column("大小", key="size", width=10)
        table.add_column("路径", key="path")

        if not self.scan_data.projects:
            return

        self._selected = set(range(len(self.scan_data.projects)))
        for i, proj in enumerate(self.scan_data.projects):
            sessions = len(proj.sessions)
            history = len(proj.history_entries)
            size = format_size(estimate_project_size(claude_dir, proj))
            table.add_row(
                "✓", proj.original_path,
                str(sessions), str(history), size,
                proj.original_path, key=str(i),
            )
        progress.update(progress=100)
        status.update(
            f"✓ 发现 {len(self.scan_data.projects)} 个项目 | "
            f"已选 {len(self._selected)} | "
            "方向键导航 空格选择 点击表头排序"
        )

    # --- 排序 ---

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = event.column_key.value if event.column_key else None
        if col_key is None or col_key == "check":
            return
        if self._sort_col == col_key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = str(col_key)
            self._sort_asc = True
        self._resort()

    def _resort(self) -> None:
        if self.scan_data is None:
            return
        table = self.query_one("#project-table", DataTable)
        col = self._sort_col
        claude_dir = Path.home() / ".claude"

        def sort_key(idx: int) -> object:
            proj = self.scan_data.projects[idx]
            if col == "project":
                return proj.original_path.lower()
            elif col == "sessions":
                return len(proj.sessions)
            elif col == "history":
                return len(proj.history_entries)
            elif col == "size":
                return estimate_project_size(claude_dir, proj)
            elif col == "path":
                return proj.original_path.lower()
            return 0

        indices = sorted(range(len(self.scan_data.projects)), key=sort_key,
                         reverse=not self._sort_asc)
        table.clear()
        for i in indices:
            proj = self.scan_data.projects[i]
            sessions = len(proj.sessions)
            history = len(proj.history_entries)
            size = format_size(estimate_project_size(claude_dir, proj))
            check = "✓" if i in self._selected else " "
            table.add_row(check, proj.original_path,
                          str(sessions), str(history), size,
                          proj.original_path, key=str(i))

    # --- 选择 ---

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        self._do_toggle(advance=False)

    def action_toggle_row(self) -> None:
        self._do_toggle(advance=True)

    def _do_toggle(self, advance: bool = False) -> None:
        table = self.query_one("#project-table", DataTable)
        try:
            row = table.ordered_rows[table.cursor_row]
            row_key = row.key
        except (IndexError, AttributeError, KeyError):
            return
        if row_key is None:
            return
        idx = int(str(row_key.value) if hasattr(row_key, 'value') else str(row_key))
        if idx in self._selected:
            self._selected.discard(idx)
        else:
            self._selected.add(idx)
        self._update_row_check(table, idx)
        self._update_status()
        if advance and table.cursor_row < table.row_count - 1:
            table.action_cursor_down()

    def _update_row_check(self, table: DataTable, idx: int) -> None:
        try:
            check = "✓" if idx in self._selected else " "
            table.update_cell(str(idx), "check", check)
        except Exception:
            pass

    def _update_status(self) -> None:
        try:
            status = self.query_one("#scan-status", Label)
            if self.scan_data:
                status.update(
                    f"✓ 发现 {len(self.scan_data.projects)} 个项目 | "
                    f"已选 {len(self._selected)} | "
                    "方向键导航 空格选择 点击表头排序"
                )
        except Exception:
            pass

    @on(Button.Pressed, "#btn-all")
    def action_select_all(self) -> None:
        if self.scan_data is None:
            return
        table = self.query_one("#project-table", DataTable)
        self._selected = set(range(len(self.scan_data.projects)))
        for i in self._selected:
            self._update_row_check(table, i)
        self._update_status()

    @on(Button.Pressed, "#btn-none")
    def select_none(self) -> None:
        if self.scan_data is None:
            return
        table = self.query_one("#project-table", DataTable)
        to_clear = list(self._selected)
        self._selected.clear()
        for i in to_clear:
            self._update_row_check(table, i)
        self._update_status()

    @on(Button.Pressed, "#btn-home")
    def on_home(self) -> None:
        navigate_home(self.app)

    @on(Button.Pressed, "#btn-confirm")
    def _do_confirm(self) -> None:
        if self.scan_data is None:
            return
        if not self._selected:
            self.app.push_screen(MessageScreen("请至少选择一个项目。"))
            return
        selected = [self.scan_data.projects[i] for i in sorted(self._selected)]
        self.app.push_screen(PackConfigScreen(self.scan_data, selected))


# ═══════════════════════════════════════════════
# Pack Config Screen
# ═══════════════════════════════════════════════

class PackConfigScreen(Screen):
    """配置打包选项：筛选会话 + 指定输出文件."""

    BINDINGS = [
        Binding("space", "toggle_session", "选择/取消"),
    ]

    _sort_col: str = "project"
    _sort_asc: bool = True
    _selected_uuids: set[str] = set()
    _all_uuids: list[str] = []
    _session_info: dict[str, tuple] = {}

    def __init__(self, data: ClaudeData, selected: list[ProjectEntry]) -> None:
        super().__init__()
        self.data = data
        self.selected = selected

    def compose(self) -> ComposeResult:
        total = sum(len(p.sessions) for p in self.selected)
        yield Header(show_clock=True)
        with Container(id="config-container"):
            yield Label(f"已选 {len(self.selected)} 个项目，共 {total} 个会话", id="config-title", classes="title")
            yield Label("空格选择 双击切换 点击表头排序", classes="subtitle")
            with VerticalScroll(id="session-scroll"):
                yield DataTable(id="session-table", cursor_type="row")
            yield Label("输出文件路径", classes="label-hint")
            with Horizontal(id="output-row"):
                yield Input(
                    value=str(Path.home() / f"claude-migration-{timestamp_str()}.tar.gz"),
                    id="output-path",
                )
                yield Button("\U0001F4C2", variant="default", id="btn-browse-out", classes="browse-btn")
            with Horizontal(classes="btn-row"):
                yield Button("全选", variant="default", id="btn-all-sess")
                yield Button("取消全选", variant="default", id="btn-none-sess")
                yield Button("返回", variant="default", id="btn-back")
                yield Button("预览", variant="default", id="btn-preview")
                yield Button("返回主页", variant="default", id="btn-home")
                yield Button("开始打包 →", variant="primary", id="btn-start")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.add_column("", width=3, key="check")
        table.add_column("会话", key="uuid", width=14)
        table.add_column("项目", key="project")
        table.add_column("消息", key="messages", width=7)
        table.add_column("历史", key="history", width=7)
        table.add_column("文件", key="files", width=5)
        table.add_column("任务", key="tasks", width=5)
        table.add_column("修改时间", key="mtime", width=18)
        table.add_column("最近消息", key="preview")

        from datetime import datetime
        summaries = {}
        for proj in self.selected:
            summaries.update(get_session_summaries(proj))

        self._all_uuids = []
        for proj in self.selected:
            for s in proj.sessions:
                self._all_uuids.append(s.uuid)
                msg_count = count_jsonl_lines(s.jsonl_path) if s.jsonl_path else 0
                hist_count = sum(1 for e in proj.history_entries if e.get("sessionId") == s.uuid)
                mtime = ""
                if s.jsonl_path and s.jsonl_path.exists():
                    ts = s.jsonl_path.stat().st_mtime
                    mtime = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                preview = summaries.get(s.uuid, "")
                self._session_info[s.uuid] = (proj, s, msg_count, hist_count, mtime)

        self._selected_uuids = set(self._all_uuids)
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.clear()
        for uuid in self._all_uuids:
            proj, sess, msg_count, hist_count, mtime = self._session_info[uuid]
            check = "✓" if uuid in self._selected_uuids else " "
            fh = "✓" if sess.has_file_history else "-"
            tk = "✓" if sess.has_tasks else "-"
            preview = get_session_summaries(proj).get(uuid, "")
            table.add_row(
                check, uuid[:12], proj.original_path,
                str(msg_count), str(hist_count), fh, tk,
                mtime, preview, key=uuid,
            )

    # --- 选择 ---

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        self._do_toggle_session(advance=False)

    def action_toggle_session(self) -> None:
        self._do_toggle_session(advance=True)

    def _do_toggle_session(self, advance: bool = False) -> None:
        table = self.query_one("#session-table", DataTable)
        try:
            row = table.ordered_rows[table.cursor_row]
            uuid = str(row.key.value) if hasattr(row.key, 'value') else str(row.key)
        except (IndexError, AttributeError, KeyError):
            return
        if uuid in self._selected_uuids:
            self._selected_uuids.discard(uuid)
        else:
            self._selected_uuids.add(uuid)
        try:
            check = "✓" if uuid in self._selected_uuids else " "
            table.update_cell(uuid, "check", check)
        except Exception:
            pass
        self._update_session_status()
        if advance and table.cursor_row < table.row_count - 1:
            table.action_cursor_down()

    @on(Button.Pressed, "#btn-all-sess")
    def select_all_sessions(self) -> None:
        table = self.query_one("#session-table", DataTable)
        for uuid in self._all_uuids:
            self._selected_uuids.add(uuid)
            try:
                table.update_cell(uuid, "check", "✓")
            except Exception:
                pass
        self._update_session_status()

    @on(Button.Pressed, "#btn-none-sess")
    def select_none_sessions(self) -> None:
        table = self.query_one("#session-table", DataTable)
        to_clear = list(self._selected_uuids)
        self._selected_uuids.clear()
        for uuid in to_clear:
            try:
                table.update_cell(uuid, "check", " ")
            except Exception:
                pass
        self._update_session_status()

    def _update_session_status(self) -> None:
        try:
            title = self.query_one("#config-title", Label)
            title.update(
                f"已选 {len(self.selected)} 个项目，共 {len(self._all_uuids)} 个会话 | "
                f"已选 {len(self._selected_uuids)} | "
                "空格选择 双击切换 点击表头排序"
            )
        except Exception:
            pass

    # --- 排序 ---

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = event.column_key.value if event.column_key else None
        if col_key is None or col_key in ("check",):
            return
        if self._sort_col == col_key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = str(col_key)
            self._sort_asc = True
        self._resort_sessions()

    def _resort_sessions(self) -> None:
        col = self._sort_col
        rev = not self._sort_asc

        def key(uuid: str) -> object:
            proj, sess, msg_count, hist_count, mtime = self._session_info[uuid]
            if col == "uuid":
                return uuid
            elif col == "project":
                return proj.original_path.lower()
            elif col == "messages":
                return msg_count
            elif col == "history":
                return hist_count
            elif col == "files":
                return (1 if sess.has_file_history else 0)
            elif col == "tasks":
                return (1 if sess.has_tasks else 0)
            elif col == "mtime":
                return mtime
            elif col == "preview":
                return get_session_summaries(proj).get(uuid, "").lower()
            return 0

        self._all_uuids.sort(key=key, reverse=rev)
        self._render_table()

    # --- 操作 ---

    @on(Button.Pressed, "#btn-preview")
    def on_preview(self) -> None:
        table = self.query_one("#session-table", DataTable)
        try:
            row = table.ordered_rows[table.cursor_row]
            uuid = str(row.key.value) if hasattr(row.key, 'value') else str(row.key)
        except (IndexError, AttributeError, KeyError):
            return
        if uuid and uuid in self._session_info:
            proj, sess, _, _, _ = self._session_info[uuid]
            self.app.push_screen(SessionPreviewScreen(uuid, proj, sess))

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-home")
    def on_home(self) -> None:
        navigate_home(self.app)

    @on(Button.Pressed, "#btn-browse-out")
    def on_browse_output(self) -> None:
        path = open_file_dialog(save=True)
        if path:
            self.query_one("#output-path", Input).value = path

    @on(Button.Pressed, "#btn-start")
    def on_start(self) -> None:
        if not self._selected_uuids:
            self.app.push_screen(MessageScreen("请至少选择一个会话。"))
            return
        output_path = self.query_one("#output-path", Input).value.strip()
        if not output_path:
            self.app.push_screen(MessageScreen("请指定输出文件路径。"))
            return
        self.app.push_screen(
            PackProgressScreen(self.data, self.selected, output_path, self._selected_uuids)
        )


# ═══════════════════════════════════════════════
# Pack Progress Screen
# ═══════════════════════════════════════════════

class PackProgressScreen(Screen):
    """打包进度和结果."""

    BINDINGS = [
    ]

    def __init__(self, data: ClaudeData, selected: list[ProjectEntry],
                 output_path: str, session_filter: set[str]) -> None:
        super().__init__()
        self.data = data
        self.selected = selected
        self.output_path = output_path
        self.session_filter = session_filter
        self._pack_output = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="pack-container"):
            yield Label("开始打包", classes="title")
            yield Static("", id="pack-detail")
            with Vertical(id="pack-progress-wrap"):
                yield ProgressBar(id="pack-progress", total=100)
                yield Label("准备中...", id="pack-step")
            with Vertical(id="pack-result-box"):
                yield Static("", id="pack-result")
            with Horizontal(classes="btn-row"):
                yield Button("打开文件夹", variant="default", id="btn-open-folder")
                yield Button("返回主菜单", variant="primary", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._do_pack(), exclusive=True)

    async def _do_pack(self) -> None:
        detail = self.query_one("#pack-detail", Static)
        progress = self.query_one("#pack-progress", ProgressBar)
        step = self.query_one("#pack-step", Label)
        result = self.query_one("#pack-result", Static)

        count = len(self.session_filter)
        proj_count = len(self.selected)
        detail.update(
            f"[dim]{proj_count} 个项目 · {count} 个会话[/dim]\n"
            f"[dim]输出: {self.output_path}[/dim]"
        )

        step.update("收集会话文件...")
        progress.advance(15)
        await asyncio.sleep(0.15)
        step.update("复制 file-history...")
        progress.advance(15)
        await asyncio.sleep(0.15)
        step.update("复制 tasks 数据...")
        progress.advance(10)
        await asyncio.sleep(0.15)
        step.update("提取 history.jsonl...")
        progress.advance(10)
        await asyncio.sleep(0.15)

        try:
            step.update("打包压缩中...")
            progress.advance(20)
            output = pack(self.data, self.selected, self.output_path,
                          session_filter=self.session_filter)
            progress.advance(25)
            self._pack_output = output
            total_size = output.stat().st_size

            lines = [
                "[bold green]✓ 打包完成![/bold green]", "",
                f"[bold]输出文件:[/bold] {output}",
                f"[bold]文件大小:[/bold] {format_size(total_size)}", "",
                f"[bold]项目数:[/bold] {proj_count}",
                f"[bold]会话数:[/bold] {count}", "",
            ]
            for proj in self.selected:
                active = len([s for s in proj.sessions if s.uuid in self.session_filter])
                lines.append(f"  [dim]{proj.original_path}[/dim]: {active} 会话")
            result.update("\n".join(lines))
            progress.update(progress=100)
            step.update("完成")
        except Exception as e:
            result.update(f"[bold red]✗ 打包失败: {e}[/bold red]")
            progress.update(progress=100)

    @on(Button.Pressed, "#btn-open-folder")
    def on_open_folder(self) -> None:
        if self._pack_output is None:
            return
        folder = self._pack_output.parent
        if folder.exists():
            subprocess.run(["xdg-open", str(folder)], capture_output=True)

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        navigate_home(self.app)
