from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView

from ..auth import verify_password

class UnlockScreen(ModalScreen[None]):
	def compose(self) -> ComposeResult:
		with Container(id="auth-modal"):
			yield Label("验证你的身份", classes="title")
			yield Input(password=True, id="auth-password", placeholder="输入解锁密码")
			yield Label("", id="auth-error")
			with Horizontal(id="auth-btn-row"):
				yield Button("确认", variant="primary", id="btn-auth-ok")
				yield Button("取消", variant="default", id="btn-auth-cancel")

	def on_mount(self) -> None:
		self.query_one("#auth-password", Input).focus()

	@on(Input.Submitted, "#auth-password")
	def on_auth_submit(self) -> None:
		self._do_auth()

	@on(Button.Pressed, "#btn-auth-ok")
	def on_auth_ok(self) -> None:
		self._do_auth()

	def _do_auth(self) -> None:
		password = self.query_one("#auth-password", Input).value
		if verify_password(password):
			self.app.push_screen(FileSelectScreen())
		else:
			self.query_one("#auth-error", Label).update("[red]密码错误[/red]")

	@on(Button.Pressed, "#btn-auth-cancel")
	def on_auth_cancel(self) -> None:
		self.dismiss()

class FileSelectScreen(ModalScreen[None]):
	"""选择要编辑的文件."""

	BINDINGS = [
		Binding("ctrl+c", "back_to_help", "返回帮助", priority=True),
	]

	HELP_DIR = Path(__file__).parent.parent / "help"
	CSS_DIR = Path(__file__).parent / "css"

	def action_back_to_help(self) -> None:
		# 弹出 FileSelectScreen + UnlockScreen，回到 HelpScreen
		for _ in range(2):
			try:
				self.app.pop_screen()
			except Exception:
				break

	def compose(self) -> ComposeResult:
		with Container(id="file-select-modal"):
			yield Label("选择要编辑的文件", classes="title")
			yield ListView(id="file-list")
			with Horizontal(id="file-btn-row"):
				yield Button("编辑", variant="primary", id="btn-edit-file")
				yield Button("取消", variant="default", id="btn-cancel-file")

	def on_mount(self) -> None:
		lv = self.query_one("#file-list", ListView)
		if self.HELP_DIR.exists():
			for f in sorted(self.HELP_DIR.glob("*.md")):
				lv.append(
					ListItem(Label(f"[bold]📄[/] 文档: {f.name}"), name=str(f))
				)
		if self.CSS_DIR.exists():
			for f in sorted(self.CSS_DIR.glob("*.css")):
				lv.append(
					ListItem(Label(f"[bold]🎨[/] 样式: {f.name}"), name=str(f))
				)

	def _open_editor(self) -> None:
		lv = self.query_one("#file-list", ListView)
		if lv.index is not None and lv.index < len(lv.children):
			item = lv.children[lv.index]
			name = getattr(item, "name", None)
			if name:
				from .editor import EditorScreen
				self.app.push_screen(EditorScreen(Path(name)))

	@on(Button.Pressed, "#btn-edit-file")
	def on_edit(self) -> None:
		self._open_editor()

	@on(Button.Pressed, "#btn-cancel-file")
	def on_cancel_file(self) -> None:
		self.action_back_to_help()

	@on(ListView.Selected)
	def on_item_selected(self) -> None:
		self._open_editor()
