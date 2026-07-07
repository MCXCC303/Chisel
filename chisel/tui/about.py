"""关于页面."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static


class AboutScreen(Screen):
    """关于 Chisel."""

    BINDINGS = [
        Binding("escape", "pop_screen", "返回", show=False),
    ]

    BANNER = """\
[bold #f7971f] ██████╗██╗  ██╗██╗███████╗███████╗██╗     [/bold #f7971f]
[bold #f7971f]██╔════╝██║  ██║██║██╔════╝██╔════╝██║     [/bold #f7971f]
[bold #f7971f]██║     ███████║██║███████╗█████╗  ██║     [/bold #f7971f]
[bold #f7971f]██║     ██╔══██║██║╚════██║██╔══╝  ██║     [/bold #f7971f]
[bold #f7971f]╚██████╗██║  ██║██║███████║███████╗███████╗[/bold #f7971f]
[bold #f7971f] ╚═════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝[/bold #f7971f]"""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="about-container"):
            yield Static(self.BANNER, id="about-banner")
            yield Label("Chisel - Claude Code 历史记录迁移工具", classes="title")
            yield Static("", id="about-spacer")
            yield Label("Made by MCXCC303", classes="about-text")
            yield Label("Powered by Python · Textual · Rich", classes="about-sub")
            yield Label("Inspired by opencode", classes="about-sub")
            from .. import __version__
            yield Label(f"Version {__version__}", classes="about-version")
            with Horizontal(classes="btn-row"):
                yield Button("返回", variant="primary", id="btn-back")
        yield Footer()

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.app.pop_screen()
