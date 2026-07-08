"""消息弹窗."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

class MessageScreen(ModalScreen):
	"""通用消息弹窗."""

	def __init__(self, message: str) -> None:
		super().__init__()
		self.message = message

	def compose(self) -> ComposeResult:
		with Vertical(id="msg-wrapper"):
			yield Label(self.message, classes="msg-text")
			with Horizontal(id="msg-btn-row"):
				yield Button("确定", variant="primary", id="btn-ok")

	@on(Button.Pressed, "#btn-ok")
	def on_ok(self) -> None:
		self.app.pop_screen()
