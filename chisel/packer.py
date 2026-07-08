"""打包器：将项目历史记录打包为 tar.gz 归档.

包内所有绝对路径均替换为占位符 __CM_PROJECT_N__，
解包时由用户指定真实路径后再替换。
"""

from __future__ import annotations

import json
import shutil
import socket
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .models import ClaudeData, ProjectEntry

PLACEHOLDER_PREFIX = "__CM_PROJECT_"

def _make_placeholder(index: int) -> str:
	return f"{PLACEHOLDER_PREFIX}{index}__"

def pack(
		data: ClaudeData,
		selected_projects: list[ProjectEntry],
		output_path: str | Path,
		include_global_settings: bool = True,
		session_filter: set[str] | None = None,
) -> Path:
	"""将选定项目打包为 tar.gz 归档.

	Args:
		data: 扫描得到的完整 ClaudeData
		selected_projects: 要打包的项目列表
		output_path: 输出文件路径
		include_global_settings: 是否包含 settings.json, stats-cache.json
		session_filter: 仅打包这些 UUID 的会话（None=全部）

	Returns:
		生成的 tar.gz 文件路径
	"""
	output_path = Path(output_path)
	name = output_path.name
	if not (name.endswith(".tar.gz") or name.endswith(".tgz")):
		output_path = output_path.parent / (name + ".tar.gz")

	# 如果指定了会话过滤器，过滤每个项目的会话列表
	if session_filter is not None:
		for proj in selected_projects:
			proj.sessions = [s for s in proj.sessions if s.uuid in session_filter]
			proj.history_entries = [
				e for e in proj.history_entries
				if e.get("sessionId") in session_filter
			]

	# 构建占位符映射: 原始路径 → 占位符, 占位符 → 项目元数据
	path_to_placeholder: dict[str, str] = {}
	placeholder_meta: dict[str, dict] = {}

	for i, proj in enumerate(selected_projects):
		ph = _make_placeholder(i)
		path_to_placeholder[proj.original_path] = ph
		placeholder_meta[ph] = {
			"index": i,
			"basename": Path(proj.original_path).name,
			"encoded_name": proj.encoded_name,
			"original_path": proj.original_path,
			"session_count": len(proj.sessions),
			"session_uuids": proj.session_uuids,
			"history_entry_count": len(proj.history_entries),
		}

	selected_uuids: set[str] = set()
	for proj in selected_projects:
		selected_uuids.update(proj.session_uuids)

	with tempfile.TemporaryDirectory() as tmpdir:
		tmp = Path(tmpdir)

		# --- metadata.json ---
		metadata = {
			"version": "2.0",
			"chisel_version": __version__,
			"source_host": socket.gethostname(),
			"created_at": datetime.now(timezone.utc).isoformat(),
			"project_count": len(selected_projects),
			"session_count": sum(len(p.sessions) for p in selected_projects),
			"placeholders": placeholder_meta,
		}
		_write_json(tmp / "metadata.json", metadata)

		# --- claude.json.partial ---
		partial_json = {"projects": {}}
		for proj in selected_projects:
			if proj.claude_json_data:
				ph = path_to_placeholder[proj.original_path]
				partial_json["projects"][ph] = proj.claude_json_data
		_write_json(tmp / "claude.json.partial", partial_json)

		# --- projects/<index>/<uuid>.jsonl ---
		projects_tmp = tmp / "projects"
		projects_tmp.mkdir()
		for i, proj in enumerate(selected_projects):
			proj_dir = projects_tmp / str(i)
			proj_dir.mkdir()
			for session in proj.sessions:
				if session.jsonl_path and session.jsonl_path.exists():
					content = session.jsonl_path.read_bytes()
					dest = proj_dir / f"{session.uuid}.jsonl"

					# 替换内容中的项目路径
					content = _replace_paths_in_bytes(
						content, path_to_placeholder, selected_projects
					)
					dest.write_bytes(content)

		# --- file-history/<uuid>/ ---
		fh_tmp = tmp / "file-history"
		fh_tmp.mkdir()
		file_history_dir = data.claude_dir / "file-history"
		if file_history_dir.exists():
			for uuid in selected_uuids:
				src = file_history_dir / uuid
				if src.exists():
					_copy_dir_with_replace(
						src, fh_tmp / uuid,
						path_to_placeholder, selected_projects,
					)

		# --- tasks/<uuid>/ ---
		tasks_tmp = tmp / "tasks"
		tasks_tmp.mkdir()
		tasks_dir = data.claude_dir / "tasks"
		if tasks_dir.exists():
			for uuid in selected_uuids:
				src = tasks_dir / uuid
				if src.exists():
					_copy_dir(src, tasks_tmp / uuid)

		# --- history.jsonl.partial ---
		all_history: list[dict] = []
		for proj in selected_projects:
			ph = path_to_placeholder[proj.original_path]
			for entry in proj.history_entries:
				# 序列化 → 全局替换路径 → 反序列化，确保所有字段都被处理
				raw = json.dumps(entry, ensure_ascii=False)
				raw = _str_replace_paths(raw, path_to_placeholder)
				entry_copy = json.loads(raw)
				all_history.append(entry_copy)
		all_history.sort(key=lambda e: e.get("timestamp", 0))
		if all_history:
			_write_jsonl(tmp / "history.jsonl.partial", all_history)

		# --- 全局设置 ---
		if include_global_settings:
			global_files = ["settings.json", "stats-cache.json"]
			for gf in global_files:
				src = data.claude_dir / gf
				if src.exists():
					dest = tmp / gf
					dest.write_bytes(src.read_bytes())

		# --- 打包到临时文件 ---
		tmp_archive = tmp / "archive.tar.gz"
		with tarfile.open(tmp_archive, "w:gz") as tar:
			for item in sorted(tmp.rglob("*")):
				arcname = item.relative_to(tmp)
				tar.add(item, arcname=str(arcname))

		# 移动到目标路径
		output_path.parent.mkdir(parents=True, exist_ok=True)
		shutil.move(str(tmp_archive), str(output_path))

	return output_path

def _str_replace_paths(text: str, path_to_placeholder: dict[str, str]) -> str:
	"""在字符串中替换所有项目路径为占位符."""
	for original_path, ph in path_to_placeholder.items():
		text = text.replace(original_path, ph)
	return text

def _replace_paths_in_bytes(
		data: bytes,
		path_to_placeholder: dict[str, str],
		selected_projects: list[ProjectEntry],
) -> bytes:
	"""在二进制内容中替换所有项目路径为占位符."""
	text = data.decode("utf-8", errors="replace")
	for proj in selected_projects:
		ph = path_to_placeholder[proj.original_path]
		text = text.replace(proj.original_path, ph)
	return text.encode("utf-8")

def _copy_dir_with_replace(
		src: Path,
		dest: Path,
		path_to_placeholder: dict[str, str],
		selected_projects: list[ProjectEntry],
) -> None:
	"""递归复制目录，替换文件内容中的路径."""
	dest.mkdir(parents=True, exist_ok=True)
	for item in src.rglob("*"):
		if item.is_file():
			rel = item.relative_to(src)
			target = dest / rel
			target.parent.mkdir(parents=True, exist_ok=True)
			content = _replace_paths_in_bytes(
				item.read_bytes(), path_to_placeholder, selected_projects
			)
			target.write_bytes(content)

def _write_json(path: Path, data: dict) -> None:
	path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _write_jsonl(path: Path, entries: list[dict]) -> None:
	lines = [json.dumps(e, ensure_ascii=False) for e in entries]
	path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def _copy_dir(src: Path, dest: Path) -> None:
	"""递归复制目录."""
	dest.mkdir(parents=True, exist_ok=True)
	for item in src.rglob("*"):
		if item.is_file():
			rel = item.relative_to(src)
			target = dest / rel
			target.parent.mkdir(parents=True, exist_ok=True)
			target.write_bytes(item.read_bytes())
