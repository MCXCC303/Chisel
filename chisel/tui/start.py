"""启动页面."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static


class StartScreen(Screen):
    """启动页面."""

    BINDINGS = [
        Binding("ctrl+d", "quit", "退出"),
    ]

    BANNER = """\
[bold #f7971f] ██████╗██╗  ██╗██╗███████╗███████╗██╗     [/bold #f7971f]
[bold #f7971f]██╔════╝██║  ██║██║██╔════╝██╔════╝██║     [/bold #f7971f]
[bold #f7971f]██║     ███████║██║███████╗█████╗  ██║     [/bold #f7971f]
[bold #f7971f]██║     ██╔══██║██║╚════██║██╔══╝  ██║     [/bold #f7971f]
[bold #f7971f]╚██████╗██║  ██║██║███████║███████╗███████╗[/bold #f7971f]
[bold #f7971f] ╚═════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝[/bold #f7971f]
"""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="start-container"):
            yield Static(self.BANNER, id="banner")
            yield Label("Chisel - Claude Code 历史记录迁移工具", classes="title")
            yield Label("选择要执行的操作", classes="subtitle")
            with Horizontal(classes="btn-row"):
                yield Button("打包历史记录", variant="primary", id="btn-pack", classes="action-btn")
                yield Button("解包历史记录", variant="primary", id="btn-unpack", classes="action-btn")
                yield Button("清除无效记录", variant="primary", id="btn-clean", classes="action-btn")
            with Horizontal(classes="btn-row"):
                yield Button("帮助", variant="default", id="btn-help")
                yield Button("关于", variant="default", id="btn-about")
        yield Footer()

    @on(Button.Pressed, "#btn-pack")
    def on_pack(self) -> None:
        from .pack import ScanScreen
        self.app.push_screen(ScanScreen())

    @on(Button.Pressed, "#btn-unpack")
    def on_unpack(self) -> None:
        from .unpack import UnpackSelectScreen
        self.app.push_screen(UnpackSelectScreen())

    @on(Button.Pressed, "#btn-help")
    def on_help(self) -> None:
        from .help import HelpScreen
        self.app.push_screen(HelpScreen())

    @on(Button.Pressed, "#btn-clean")
    def on_clean(self) -> None:
        from .clean import OrphanScanScreen
        self.app.push_screen(OrphanScanScreen())

    @on(Button.Pressed, "#btn-about")
    def on_about(self) -> None:
        from .about import AboutScreen
        self.app.push_screen(AboutScreen())
