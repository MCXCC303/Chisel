"""内置文本编辑器 —— 编辑帮助文档与 CSS."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.message import Message as PostMessage
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static, TextArea

class EditorScreen(Screen):
    """全屏文本编辑器."""

    BINDINGS = [
        Binding("ctrl+s", "save", "保存"),
        Binding("ctrl+c", "back_to_files", "返回文件列表", priority=True),
    ]

    def __init__(self, file_path: str | Path) -> None:
        super().__init__()
        self.file_path = Path(file_path)
        self.original_content = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            f"编辑: [bold]{self.file_path.relative_to(Path(__file__).parent.parent.parent)}[/bold]",
            id="editor-title",
        )
        with Container(id="editor-container"):
            yield TextArea.code_editor(
                language="markdown" if self.file_path.suffix == ".md" else "css",
                id="editor-textarea",
                tab_behavior="focus",
            )
        with Horizontal(classes="btn-row"):
            yield Button("取消", variant="default", id="btn-cancel")
            yield Label("", id="editor-status")
            yield Button("保存 (Ctrl+S)", variant="primary", id="btn-save")
        yield Footer()

    def on_mount(self) -> None:
        try:
            content = self.file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        self.original_content = content
        ta = self.query_one("#editor-textarea", TextArea)
        ta.load_text(content)

    def action_save(self) -> None:
        self._do_save()

    def action_back_to_files(self) -> None:
        self.dismiss()  # 弹出编辑器，恢复 FileSelectScreen

    @on(Button.Pressed, "#btn-save")
    def on_save_click(self) -> None:
        self._do_save()

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self) -> None:
        ta = self.query_one("#editor-textarea", TextArea)
        if ta.text != self.original_content:
            self._show_status("未保存的更改已丢弃", "warning")
        self.dismiss()

    def _do_save(self) -> None:
        ta = self.query_one("#editor-textarea", TextArea)
        new_content = ta.text
        try:
            self.file_path.write_text(new_content, encoding="utf-8")
            self.original_content = new_content
            self._show_status("已保存 ✓", "success")
            # 通知应用重新加载资源
            self.app.post_message(FileEdited(self.file_path))
        except OSError as e:
            self._show_status(f"保存失败: {e}", "error")

    def _show_status(self, msg: str, kind: str) -> None:
        status = self.query_one("#editor-status", Label)
        colors = {"success": "green", "warning": "#ff9800", "error": "red"}
        status.update(f"[{colors.get(kind, 'white')}]{msg}[/]")


class FileEdited(PostMessage):
    """文件已被编辑器修改的消息."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
