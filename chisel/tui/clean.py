"""清理无效路径历史记录."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
	Button, DataTable, Footer, Header, Label, ProgressBar, Static,
)

from .helpers import (
	count_jsonl_lines, estimate_project_size, format_size,
	get_session_summaries, navigate_home,
)
from .message import MessageScreen
from .preview import SessionPreviewScreen
from ..cleanup import delete_sessions, find_orphan_projects
from ..models import ClaudeData, ProjectEntry
from ..scanner import scan

class OrphanScanScreen(Screen):
	"""扫描无效路径并选择要清理的项目."""

	BINDINGS = [
		Binding("space", "toggle_row", "选择/取消"),
	]

	scan_data: ClaudeData | None = None
	_selected: set[int] = set()

	def compose(self) -> ComposeResult:
		yield Header(show_clock=True)
		with Container(id="scan-container"):
			yield Label("清除无效历史记录", classes="title")
			yield Label("正在扫描...", id="scan-status", classes="subtitle")
			yield ProgressBar(id="scan-progress", total=100)
			with VerticalScroll(id="list-container"):
				yield DataTable(id="orphan-table", cursor_type="row")
			with Horizontal(classes="btn-row"):
				yield Button("返回主页", variant="warning", id="btn-home")
				yield Button("全选", variant="default", id="btn-all")
				yield Button("取消全选", variant="default", id="btn-none")
				yield Button("下一步 →", variant="primary", id="btn-confirm")
		yield Footer()

	def on_mount(self) -> None:
		self.run_worker(self._do_scan(), exclusive=True)

	async def _do_scan(self) -> None:
		status = self.query_one("#scan-status", Label)
		progress = self.query_one("#scan-progress", ProgressBar)
		table = self.query_one("#orphan-table", DataTable)

		status.update("正在读取 ~/.claude/ ...")
		progress.advance(30)
		claude_dir = Path.home() / ".claude"
		claude_json = Path.home() / ".claude.json"
		self.scan_data = scan(claude_dir=claude_dir, claude_json_path=claude_json)
		progress.advance(30)

		status.update("正在检查项目路径...")
		orphans = find_orphan_projects(self.scan_data)
		progress.advance(30)

		table.add_column("", width=3, key="check")
		table.add_column("项目", key="project")
		table.add_column("会话", key="sessions", width=8)
		table.add_column("历史", key="history", width=8)
		table.add_column("大小", key="size", width=10)
		table.add_column("原始路径（无效）", key="path")

		if not orphans:
			status.update("✓ 没有无效路径的历史记录")
			return

		self._selected = set(range(len(orphans)))
		for i, proj in enumerate(orphans):
			sessions = len(proj.sessions)
			history = len(proj.history_entries)
			size = format_size(estimate_project_size(claude_dir, proj))
			table.add_row(
				"✓", Path(proj.original_path).name,
				str(sessions), str(history), size,
				proj.original_path, key=str(i),
			)
		progress.update(progress=100)
		status.update(
			f"✓ 发现 {len(orphans)} 个无效路径 | "
			f"已选 {len(self._selected)} | "
			"空格选择 点击表头排序"
		)

	def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
		event.stop()
		self._do_toggle(advance=False)

	def action_toggle_row(self) -> None:
		self._do_toggle(advance=True)

	def _do_toggle(self, advance: bool = False) -> None:
		table = self.query_one("#orphan-table", DataTable)
		try:
			row = table.ordered_rows[table.cursor_row]
			idx = int(str(row.key.value) if hasattr(row.key, 'value') else str(row.key))
		except (IndexError, AttributeError, KeyError):
			return
		if idx in self._selected:
			self._selected.discard(idx)
		else:
			self._selected.add(idx)
		try:
			check = "✓" if idx in self._selected else " "
			table.update_cell(str(idx), "check", check)
		except Exception:
			pass
		self._update_status()
		if advance and table.cursor_row < table.row_count - 1:
			table.action_cursor_down()

	def _update_status(self) -> None:
		try:
			orphans = find_orphan_projects(self.scan_data) if self.scan_data else []
			self.query_one("#scan-status", Label).update(
				f"✓ 发现 {len(orphans)} 个无效路径 | "
				f"已选 {len(self._selected)} | "
				"空格选择 点击表头排序"
			)
		except Exception:
			pass

	@on(Button.Pressed, "#btn-all")
	def select_all(self) -> None:
		if self.scan_data is None:
			return
		orphans = find_orphan_projects(self.scan_data)
		table = self.query_one("#orphan-table", DataTable)
		self._selected = set(range(len(orphans)))
		for i in self._selected:
			try:
				table.update_cell(str(i), "check", "✓")
			except Exception:
				pass
		self._update_status()

	@on(Button.Pressed, "#btn-none")
	def select_none(self) -> None:
		table = self.query_one("#orphan-table", DataTable)
		for i in list(self._selected):
			try:
				table.update_cell(str(i), "check", " ")
			except Exception:
				pass
		self._selected.clear()
		self._update_status()

	@on(Button.Pressed, "#btn-home")
	def on_home(self) -> None:
		navigate_home(self.app)

	@on(Button.Pressed, "#btn-confirm")
	def _do_confirm(self) -> None:
		if self.scan_data is None or not self._selected:
			self.app.push_screen(MessageScreen("请至少选择一个项目。"))
			return
		orphans = find_orphan_projects(self.scan_data)
		selected = [orphans[i] for i in sorted(self._selected)]
		self.app.push_screen(OrphanConfigScreen(self.scan_data, selected))

class OrphanConfigScreen(Screen):
	"""选择要删除的会话."""

	BINDINGS = [
		Binding("space", "toggle_session", "选择/取消"),
	]

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
			yield Label(
				f"已选 {len(self.selected)} 个无效项目，共 {total} 个会话",
				id="config-title", classes="title",
			)
			yield Label("⚠ 删除操作不可逆！默认全选，取消不需要删除的会话", classes="subtitle")
			with VerticalScroll(id="session-scroll"):
				yield DataTable(id="session-table", cursor_type="row")
			with Horizontal(classes="btn-row"):
				yield Button("返回", variant="warning", id="btn-back")
				yield Button("返回主页", variant="warning", id="btn-home")
				yield Button("全选", variant="default", id="btn-all-sess")
				yield Button("取消全选", variant="default", id="btn-none-sess")
				yield Button("预览", variant="default", id="btn-preview")
				yield Button("删除选中 →", variant="error", id="btn-delete")
		yield Footer()

	def on_mount(self) -> None:
		table = self.query_one("#session-table", DataTable)
		table.add_column("", width=3, key="check")
		table.add_column("会话", key="uuid", width=14)
		table.add_column("项目", key="project")
		table.add_column("消息", key="messages", width=7)
		table.add_column("历史", key="history", width=7)
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
				self._session_info[s.uuid] = (proj, s, msg_count, hist_count, mtime)

		self._selected_uuids = set(self._all_uuids)
		self._render_table()

	def _render_table(self) -> None:
		table = self.query_one("#session-table", DataTable)
		table.clear()
		for uuid in self._all_uuids:
			proj, sess, msg_count, hist_count, mtime = self._session_info[uuid]
			check = "✓" if uuid in self._selected_uuids else " "
			preview = get_session_summaries(proj).get(uuid, "")
			table.add_row(
				check, uuid[:12], Path(proj.original_path).name,
				str(msg_count), str(hist_count), mtime, preview,
				key=uuid,
			)

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
			table.update_cell(uuid, "check", "✓" if uuid in self._selected_uuids else " ")
		except Exception:
			pass
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

	@on(Button.Pressed, "#btn-none-sess")
	def select_none_sessions(self) -> None:
		table = self.query_one("#session-table", DataTable)
		for uuid in list(self._selected_uuids):
			try:
				table.update_cell(uuid, "check", " ")
			except Exception:
				pass
		self._selected_uuids.clear()

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

	@on(Button.Pressed, "#btn-delete")
	def on_delete(self) -> None:
		if not self._selected_uuids:
			self.app.push_screen(MessageScreen("请至少选择一个会话。"))
			return
		self.app.push_screen(
			ConfirmDeleteScreen(self.data, self._selected_uuids)
		)

class ConfirmDeleteScreen(Screen):
	"""二次确认删除操作."""

	BINDINGS = [
	]

	def __init__(self, data: ClaudeData, selected_uuids: set[str]) -> None:
		super().__init__()
		self.data = data
		self.selected_uuids = selected_uuids

	def compose(self) -> ComposeResult:
		yield Header(show_clock=True)
		with Container(id="about-container"):
			yield Label("⚠ 确认删除", classes="title")
			yield Label(
				f"即将永久删除 {len(self.selected_uuids)} 个会话的所有历史记录。",
				classes="subtitle",
			)
			yield Label("此操作不可逆！删除后无法恢复。", classes="about-sub")
			yield Label("", id="about-spacer")
			with Horizontal(classes="btn-row"):
				yield Button("返回（取消）", variant="default", id="btn-back")
				yield Button("确认删除", variant="error", id="btn-confirm-delete")
		yield Footer()

	@on(Button.Pressed, "#btn-back")
	def on_back(self) -> None:
		self.app.pop_screen()

	@on(Button.Pressed, "#btn-confirm-delete")
	def on_confirm(self) -> None:
		self.app.push_screen(
			OrphanProgressScreen(self.data, self.selected_uuids)
		)

class OrphanProgressScreen(Screen):
	"""删除进度和结果."""

	BINDINGS = [
	]

	def __init__(self, data: ClaudeData, selected_uuids: set[str]) -> None:
		super().__init__()
		self.data = data
		self.selected_uuids = selected_uuids

	def compose(self) -> ComposeResult:
		yield Header(show_clock=True)
		with Container(id="pack-container"):
			yield Label("正在删除...", classes="title")
			yield Static("", id="pack-detail")
			with Vertical(id="pack-progress-wrap"):
				yield ProgressBar(id="pack-progress", total=100)
				yield Label("准备中...", id="pack-step")
			with Vertical(id="pack-result-box"):
				yield Static("", id="pack-result")
			with Horizontal(classes="btn-row"):
				yield Button("返回主菜单", variant="warning", id="btn-back")
		yield Footer()

	def on_mount(self) -> None:
		self.run_worker(self._do_delete(), exclusive=True)

	async def _do_delete(self) -> None:
		detail = self.query_one("#pack-detail", Static)
		progress = self.query_one("#pack-progress", ProgressBar)
		step = self.query_one("#pack-step", Label)
		result = self.query_one("#pack-result", Static)

		count = len(self.selected_uuids)
		claude_dir = Path.home() / ".claude"
		claude_json = Path.home() / ".claude.json"
		detail.update(f"[dim]{count} 个会话[/dim]")

		step.update("Dry-run 预览...")
		progress.advance(10)
		await asyncio.sleep(0.15)

		try:
			dry = delete_sessions(self.data, self.selected_uuids, claude_dir, claude_json, dry_run=True)
			step.update(f"将删除 {dry['sessions_deleted']} 个会话")
			progress.advance(15)
			await asyncio.sleep(0.15)

			step.update("删除会话文件...")
			progress.advance(20)
			await asyncio.sleep(0.15)

			step.update("清理 file-history...")
			progress.advance(15)
			await asyncio.sleep(0.15)

			step.update("清理 tasks...")
			progress.advance(10)
			await asyncio.sleep(0.15)

			step.update("更新 history.jsonl...")
			progress.advance(10)
			await asyncio.sleep(0.15)

			report = delete_sessions(self.data, self.selected_uuids, claude_dir, claude_json, dry_run=False)
			progress.advance(15)

			lines = [
				"[bold green]✓ 清除完成![/bold green]", "",
				f"[bold]会话已删除:[/bold] {report['sessions_deleted']}",
				f"[bold]文件历史:[/bold] {report['file_history_deleted']}",
				f"[bold]任务数据:[/bold] {report['tasks_deleted']}",
				f"[bold]历史条目移除:[/bold] {report['history_entries_removed']}",
			]
			if report["errors"]:
				lines.append("")
				lines.append("[bold red]错误:[/bold red]")
				for e in report["errors"]:
					lines.append(f"  [red]{e}[/red]")
			result.update("\n".join(lines))
			progress.update(progress=100)
			step.update("完成")
		except Exception as e:
			result.update(f"[bold red]✗ 删除失败: {e}[/bold red]")
			progress.update(progress=100)

	@on(Button.Pressed, "#btn-back")
	def on_back(self) -> None:
		navigate_home(self.app)
