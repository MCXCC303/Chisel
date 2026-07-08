"""解包流程页面."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Header, Input,
    Label, ProgressBar, Static,
)

from ..unpacker import read_package_info, unpack, validate_package
from .helpers import (
    default_target_path, has_special_chars, navigate_home,
    open_file_dialog, resolve_target_dir,
)
from .message import MessageScreen


class UnpackSelectScreen(Screen):
    """选择要解包的迁移包文件."""

    BINDINGS = [
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="unpack-select-container"):
            yield Label("解包历史记录", classes="title")
            yield Label("输入迁移包文件路径 (.tar.gz)", classes="subtitle")
            with Horizontal(id="pkg-row"):
                yield Input(
                    placeholder=str(Path.home() / "claude-migration-*.tar.gz"),
                    id="package-path",
                )
                yield Button("\U0001F4C2", variant="default", id="btn-browse-pkg", classes="browse-btn")
            yield Label("目标 .claude 目录 (留空使用默认)", classes="label-hint")
            with Horizontal(id="target-row"):
                yield Input(placeholder=str(Path.home() / ".claude"), id="target-dir")
                yield Button("\U0001F4C2", variant="default", id="btn-browse-target", classes="browse-btn")
            yield Label("目标 .claude.json 路径 (留空使用默认)", classes="label-hint")
            yield Input(placeholder=str(Path.home() / ".claude.json"), id="target-json")
            with Horizontal(classes="btn-row"):
                yield Button("返回", variant="default", id="btn-back")
                yield Button("返回主页", variant="default", id="btn-home")
                yield Button("下一步 →", variant="primary", id="btn-next")
        yield Footer()

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-home")
    def on_home(self) -> None:
        navigate_home(self.app)

    @on(Button.Pressed, "#btn-browse-pkg")
    def on_browse_pkg(self) -> None:
        path = open_file_dialog()
        if path:
            self.query_one("#package-path", Input).value = path

    @on(Button.Pressed, "#btn-browse-target")
    def on_browse_target(self) -> None:
        path = open_file_dialog(directory=True)
        if path:
            claude_dir, claude_json = resolve_target_dir(path)
            self.query_one("#target-dir", Input).value = claude_dir
            self.query_one("#target-json", Input).value = claude_json

    @on(Button.Pressed, "#btn-next")
    def on_next(self) -> None:
        pkg_path = self.query_one("#package-path", Input).value.strip()
        target_dir = self.query_one("#target-dir", Input).value.strip()
        target_json = self.query_one("#target-json", Input).value.strip()
        if not pkg_path:
            self.app.push_screen(MessageScreen("请输入迁移包文件路径。"))
            return
        pkg = Path(pkg_path)
        if not pkg.exists():
            self.app.push_screen(MessageScreen(f"文件不存在: {pkg_path}"))
            return

        errors = validate_package(pkg_path)
        if errors:
            msg = "包校验失败:\n\n" + "\n".join(f"  • {e}" for e in errors[:8])
            if len(errors) > 8:
                msg += f"\n  • ... 还有 {len(errors) - 8} 个错误"
            self.app.push_screen(MessageScreen(msg))
            return

        if not target_dir:
            target_dir = str(Path.home() / ".claude")
        if not target_json:
            target_dir, target_json = resolve_target_dir(target_dir)
        self.app.push_screen(UnpackMapScreen(pkg_path, target_dir, target_json))


class UnpackMapScreen(Screen):
    """配置占位符到新路径的映射."""

    BINDINGS = [
    ]

    def __init__(self, pkg_path: str, target_dir: str, target_json: str) -> None:
        super().__init__()
        self.pkg_path = pkg_path
        self.target_dir = target_dir
        self.target_json = target_json
        self.info: dict = {}
        self.placeholders: list[tuple[str, dict]] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="unpack-map-container"):
            yield Label("配置项目路径映射", classes="title")
            yield Label("为包中的每个项目指定新环境上的路径", classes="subtitle")
            yield Static("", id="path-warning", classes="subtitle")
            yield VerticalScroll(id="map-inputs")
            with Horizontal(classes="btn-row"):
                yield Button("返回", variant="default", id="btn-back")
                yield Button("返回主页", variant="default", id="btn-home")
                yield Button("开始解包 →", variant="primary", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.info = read_package_info(self.pkg_path)
            pkg_ver = self.info.get("chisel_version", "unknown")
            from .. import __version__
            if pkg_ver != "unknown" and pkg_ver != __version__:
                self.notify(
                    f"⚠ 包版本 {pkg_ver} 与当前 Chisel {__version__} 不同，可能存在兼容性问题",
                    severity="warning", timeout=8,
                )
        except Exception as e:
            self.app.push_screen(MessageScreen(f"无法读取包文件: {e}"))
            return

        phs = self.info.get("placeholders", {})
        if not phs:
            self.app.push_screen(MessageScreen("包中没有找到项目数据。"))
            return

        self.placeholders = list(phs.items())

        # 检查路径是否含特殊字符，显示警告
        has_warning = False
        for _, meta in self.placeholders:
            original = meta.get("original_path", "")
            if has_special_chars(original):
                has_warning = True
                break
        if has_warning:
            self.query_one("#path-warning", Static).update(
                "[bold #ff9800]⚠ 包中含有中文或特殊字符路径，建议映射到纯 ASCII 路径以避免编码碰撞[/bold #ff9800]"
            )

        container = self.query_one("#map-inputs", VerticalScroll)
        for ph, meta in self.placeholders:
            basename = meta.get("basename", "unknown")
            sessions = meta.get("session_count", 0)
            original = meta.get("original_path", "")
            default_path = default_target_path(original, basename)
            container.mount(Static(
                f"项目: [bold]{basename}[/bold] ({sessions} 个会话)",
                classes="map-label",
            ))
            row = Horizontal(classes="map-row")
            container.mount(row)
            row.mount(Input(placeholder=default_path, id=f"map-{ph}", classes="map-input"))
            row.mount(Button("\U0001F4C2", variant="default", id=f"btn-browse-{ph}", classes="browse-btn"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("btn-browse-"):
            ph = btn_id[len("btn-browse-"):]
            path = open_file_dialog(directory=True)
            if path:
                try:
                    self.query_one(f"#map-{ph}", Input).value = path
                except Exception:
                    pass
            event.stop()

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-home")
    def on_home(self) -> None:
        navigate_home(self.app)

    @on(Button.Pressed, "#btn-next")
    def on_next(self) -> None:
        mapping: dict[str, str] = {}
        for ph, meta in self.placeholders:
            inp = self.query_one(f"#map-{ph}", Input)
            new_path = inp.value.strip()
            if new_path:
                mapping[ph] = new_path
            else:
                basename = meta.get("basename", "unknown")
                original = meta.get("original_path", "")
                mapping[ph] = default_target_path(original, basename)
        self.app.push_screen(UnpackProgressScreen(self.pkg_path, self.target_dir, self.target_json, mapping))


class UnpackProgressScreen(Screen):
    """解包进度和结果."""

    BINDINGS = [
    ]

    def __init__(self, pkg_path: str, target_dir: str, target_json: str,
                 mapping: dict[str, str]) -> None:
        super().__init__()
        self.pkg_path = pkg_path
        self.target_dir = target_dir
        self.target_json = target_json
        self.mapping = mapping

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="unpack-progress-container"):
            yield Label("开始解包", classes="title")
            yield Static("", id="unpack-detail")
            with Vertical(id="unpack-progress-wrap"):
                yield ProgressBar(id="unpack-progress", total=100)
                yield Label("准备中...", id="unpack-step")
            with Vertical(id="unpack-result-box"):
                yield Static("", id="unpack-result")
            with Horizontal(classes="btn-row"):
                yield Button("返回主菜单", variant="primary", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._do_unpack(), exclusive=True)

    async def _do_unpack(self) -> None:
        detail = self.query_one("#unpack-detail", Static)
        progress = self.query_one("#unpack-progress", ProgressBar)
        step = self.query_one("#unpack-step", Label)
        result = self.query_one("#unpack-result", Static)

        proj_count = len(self.mapping)
        detail.update(f"[dim]{proj_count} 个项目[/dim]")

        step.update("Dry-run 预览检查...")
        progress.advance(10)
        await asyncio.sleep(0.15)

        try:
            dry_report = unpack(self.pkg_path, self.target_dir, self.target_json,
                                placeholder_to_path=self.mapping, dry_run=True)
            step.update(f"预览: {dry_report['sessions_copied']} 个会话待复制")
            progress.advance(15)
            await asyncio.sleep(0.15)

            step.update("写入会话文件...")
            progress.advance(15)
            await asyncio.sleep(0.15)
            step.update("合并 claude.json...")
            progress.advance(10)
            await asyncio.sleep(0.15)
            step.update("复制 file-history...")
            progress.advance(10)
            await asyncio.sleep(0.15)
            step.update("追加 history.jsonl...")
            progress.advance(10)
            await asyncio.sleep(0.15)

            report = unpack(self.pkg_path, self.target_dir, self.target_json,
                            placeholder_to_path=self.mapping, dry_run=False)
            progress.advance(25)

            lines = [
                "[bold green]✓ 解包完成![/bold green]", "",
                f"[bold]目标目录:[/bold] {self.target_dir}", "",
                f"[bold]项目已合并:[/bold] {report['projects_merged']}",
                f"[bold]会话已复制:[/bold] {report['sessions_copied']}",
                f"[bold]会话已更新:[/bold] {report.get('sessions_updated', 0)}",
                f"[bold]会话已跳过:[/bold] {report['sessions_skipped']}",
                f"[bold]文件历史:[/bold] {report['file_history_copied']}",
                f"[bold]任务数据:[/bold] {report['tasks_copied']}",
                f"[bold]历史条目追加:[/bold] {report['history_entries_appended']}",
                "", "[bold]路径映射:[/bold]",
            ]
            for ph, path in self.mapping.items():
                lines.append(f"  [dim]{ph}[/dim] → {path}")
            result.update("\n".join(lines))
            progress.update(progress=100)
            step.update("完成")
        except Exception as e:
            result.update(f"[bold red]✗ 解包失败: {e}[/bold red]")
            progress.update(progress=100)

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        navigate_home(self.app)
