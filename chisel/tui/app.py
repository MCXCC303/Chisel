"""Chisel 主应用."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.css.stylesheet import Stylesheet

from .editor import FileEdited
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
	"editor.css",
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
		Binding("ctrl+c", "safe_back", "返回", priority=True),
		Binding("ctrl+d", "quit", "退出", priority=True),
	]

	def on_mount(self) -> None:
		self.push_screen(StartScreen())

	def action_safe_back(self) -> None:
		"""安全返回：仅在有多个用户 screen 时弹出，不弹出根页面."""
		if len(self._screen_stack) <= 2:
			return  # 仅剩 _default + 当前页，不再弹出
		self.pop_screen()

	def on_file_edited(self, message: FileEdited) -> None:
		"""编辑器保存文件后热重载."""
		if message.path.suffix == ".css":
			new_css = _load_css()
			sheet = Stylesheet()
			sheet.read_all(new_css)

			def _apply_recursive(node):
				sheet.apply(node)
				for child in node.children:
					_apply_recursive(child)

			_apply_recursive(self)
			self.stylesheet = sheet
			self.screen.refresh(repaint=True)
		elif message.path.suffix == ".md":
			# 清除帮助缓存，下次打开自动重新加载
			from .help import HELP_SECTIONS
			HELP_SECTIONS.clear()
