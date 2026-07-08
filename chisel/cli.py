"""CLI 入口：交互模式启动全屏 TUI，也支持命令行子命令."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .packer import pack
from .scanner import scan
from .unpacker import read_package_info, unpack

def main() -> None:
	parser = argparse.ArgumentParser(
		description="Chisel - Claude Code 历史记录迁移工具",
		prog="chisel",
	)
	subparsers = parser.add_subparsers(dest="command", help="子命令")

	# --- scan ---
	scan_parser = subparsers.add_parser("scan", help="扫描并列出项目")
	scan_parser.add_argument("--claude-dir", type=str, default=None)
	scan_parser.add_argument("--claude-json", type=str, default=None)

	# --- pack ---
	pack_parser = subparsers.add_parser("pack", help="打包项目历史记录")
	pack_parser.add_argument("--claude-dir", type=str, default=None)
	pack_parser.add_argument("--claude-json", type=str, default=None)
	pack_parser.add_argument(
		"-p", "--project", type=str, action="append", dest="projects",
		help="项目路径 (可多次指定)",
	)
	pack_parser.add_argument("-o", "--output", type=str, required=True)

	# --- info ---
	info_parser = subparsers.add_parser("info", help="查看包信息")
	info_parser.add_argument("package", type=str, help="迁移包 .tar.gz 路径")

	# --- unpack ---
	unpack_parser = subparsers.add_parser("unpack", help="解包历史记录")
	unpack_parser.add_argument("package", type=str, help="迁移包 .tar.gz 路径")
	unpack_parser.add_argument("--target-dir", type=str, default=None)
	unpack_parser.add_argument("--target-json", type=str, default=None)
	unpack_parser.add_argument(
		"--map", type=str, action="append", dest="mappings",
		help="占位符=新路径 (可多次指定)",
	)
	unpack_parser.add_argument("--dry-run", action="store_true")

	args = parser.parse_args()

	if args.command is None:
		_interactive_mode()
	elif args.command == "scan":
		_cmd_scan(args)
	elif args.command == "pack":
		_cmd_pack(args)
	elif args.command == "info":
		_cmd_info(args)
	elif args.command == "unpack":
		_cmd_unpack(args)

def _interactive_mode() -> None:
	"""启动全屏 TUI."""
	from .tui import ChiselApp
	app = ChiselApp()
	app.run()

def _cmd_scan(args) -> None:
	data = scan(claude_dir=args.claude_dir, claude_json_path=args.claude_json)
	for proj in data.projects:
		print(f"{proj.original_path}")
		print(f"  encoded: {proj.encoded_name}")
		print(f"  sessions: {len(proj.sessions)}")
		print(f"  history: {len(proj.history_entries)}")
		print()

def _cmd_pack(args) -> None:
	data = scan(claude_dir=args.claude_dir, claude_json_path=args.claude_json)
	if args.projects:
		selected = [p for p in data.projects if p.original_path in args.projects]
	else:
		selected = list(data.projects)
	if not selected:
		print("未找到匹配的项目。", file=sys.stderr)
		return
	output = pack(data, selected, args.output)
	print(f"打包完成: {output}")

def _cmd_info(args) -> None:
	import json
	info = read_package_info(args.package)
	print(json.dumps(info, ensure_ascii=False, indent=2))

def _cmd_unpack(args) -> None:
	placeholder_to_path = {}
	if args.mappings:
		for m in args.mappings:
			ph, new_path = m.split("=", 1)
			placeholder_to_path[ph] = new_path

	target_dir = args.target_dir or str(Path.home() / ".claude")
	target_json = args.target_json or str(Path(target_dir).parent / ".claude.json")

	report = unpack(
		args.package, target_dir, target_json,
		placeholder_to_path=placeholder_to_path,
		dry_run=args.dry_run,
	)
	for k, v in report.items():
		print(f"{k}: {v}")
