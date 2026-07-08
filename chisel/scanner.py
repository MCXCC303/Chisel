"""扫描器：发现 ~/.claude 下的项目及其历史记录."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ClaudeData, ProjectEntry, SessionEntry
from .utils import decode_project_path, encode_project_path, encode_project_path_legacy, safe_read_jsonl

def _build_path_map(projects_json: dict) -> dict[str, list[str]]:
	"""构建编码名到原始路径列表的映射（处理编码碰撞）。

	多个不同的原始路径可能编码到同一个目录名（中文/特殊字符导致）。
	返回列表以保留所有碰撞路径，供后续会话分发使用。
	"""
	path_map: dict[str, list[str]] = {}
	for original_path in projects_json:
		encoded = encode_project_path(original_path)
		path_map.setdefault(encoded, []).append(original_path)
	return path_map

def _get_session_cwd(jsonl_path: Path) -> str | None:
	"""读取会话 jsonl 首条消息，提取 cwd 字段."""
	if not jsonl_path or not jsonl_path.exists():
		return None
	try:
		with open(jsonl_path, "r", encoding="utf-8") as f:
			for line_num, line in enumerate(f):
				if line_num > 5:  # 只检查前5行
					break
				line = line.strip()
				if not line:
					continue
				try:
					msg = json.loads(line)
				except json.JSONDecodeError:
					continue
				cwd = msg.get("cwd")
				if cwd:
					return cwd
				message = msg.get("message", {})
				if isinstance(message, dict):
					cwd = message.get("cwd") or message.get("project")
					if cwd:
						return cwd
				if line_num == 0:
					break  # 只在第一条消息找
	except Exception:
		pass
	return None

def _assign_sessions_to_projects(
		sessions: list[SessionEntry],
		candidates: list[str],
		all_history: list[dict],
) -> dict[str, str]:
	"""将会话 UUID 映射到正确的原始路径。

	Priority:
	  1. history.jsonl 的 project 字段（最可靠）
	  2. 会话 jsonl 首条消息的 cwd 字段（兜底）
	"""
	result: dict[str, str] = {}

	# Method 1: history.jsonl entries
	for entry in all_history:
		sid = entry.get("sessionId")
		proj = entry.get("project")
		if sid and proj in candidates and sid not in result:
			result[sid] = proj

	# Method 2: read cwd from jsonl for unmatched sessions
	for session in sessions:
		if session.uuid in result:
			continue
		if session.jsonl_path and session.jsonl_path.exists():
			cwd = _get_session_cwd(session.jsonl_path)
			if cwd:
				for path in candidates:
					if path in cwd:
						result[session.uuid] = path
						break

	return result

def scan(
		claude_dir: str | Path | None = None,
		claude_json_path: str | Path | None = None,
) -> ClaudeData:
	"""扫描 Claude Code 数据目录。

	Args:
		claude_dir: ~/.claude/ 目录路径，默认为 ~/.claude/
		claude_json_path: ~/.claude.json 路径，默认为 ~/.claude.json

	Returns:
		ClaudeData 包含所有项目、会话等信息
	"""
	if claude_dir is None:
		claude_dir = Path.home() / ".claude"
	else:
		claude_dir = Path(claude_dir)

	if claude_json_path is None:
		claude_json_path = Path.home() / ".claude.json"
	else:
		claude_json_path = Path(claude_json_path)

	data = ClaudeData.load(claude_dir, claude_json_path)

	projects_dir = claude_dir / "projects"
	projects_json = data.claude_json.get("projects", {})

	path_map = _build_path_map(projects_json)  # encoded → list[original_path]

	# 旧编码兼容：早期 Claude Code 将 _ 也替换为 -
	legacy_path_map: dict[str, list[str]] = {}
	for original_path in projects_json:
		legacy_encoded = encode_project_path_legacy(original_path)
		legacy_path_map.setdefault(legacy_encoded, []).append(original_path)

	# 预读 history.jsonl 用于会话分配
	all_history: list[dict] = []
	history_path = claude_dir / "history.jsonl"
	if history_path.exists():
		all_history = safe_read_jsonl(history_path)

	if projects_dir.exists():
		for encoded_dir in sorted(projects_dir.iterdir()):
			if not encoded_dir.is_dir():
				continue
			encoded_name = encoded_dir.name

			# 获取所有映射到此编码名的原始路径
			project_paths = path_map.get(encoded_name)
			if project_paths is None:
				# 尝试旧编码匹配
				project_paths = legacy_path_map.get(encoded_name)
			if project_paths is None:
				decoded = decode_project_path(encoded_name)
				if decoded is None:
					continue
				project_paths = [decoded]

			# 收集所有会话
			all_sessions: list[SessionEntry] = []
			for jsonl_file in sorted(encoded_dir.glob("*.jsonl")):
				uuid = jsonl_file.stem
				has_fh = (claude_dir / "file-history" / uuid).exists()
				has_tasks = (claude_dir / "tasks" / uuid).exists()
				all_sessions.append(
					SessionEntry(
						uuid=uuid,
						has_file_history=has_fh,
						has_tasks=has_tasks,
						jsonl_path=jsonl_file,
					)
				)

			if len(project_paths) == 1:
				# 无碰撞，行为不变
				project_path = project_paths[0]
				proj_json_data = projects_json.get(project_path, {})
				history_entries = [
					e for e in all_history
					if e.get("project") == project_path
				]
				data.projects.append(
					ProjectEntry(
						original_path=project_path,
						encoded_name=encoded_name,
						claude_json_data=proj_json_data,
						sessions=all_sessions,
						history_entries=history_entries,
					)
				)
			else:
				# 碰撞：分发会话到各自的项目
				uuid_to_project = _assign_sessions_to_projects(
					all_sessions, project_paths, all_history
				)
				for project_path in project_paths:
					proj_json_data = projects_json.get(project_path, {})
					project_sessions = [
						s for s in all_sessions
						if uuid_to_project.get(s.uuid) == project_path
					]
					history_entries = [
						e for e in all_history
						if e.get("project") == project_path
					]
					data.projects.append(
						ProjectEntry(
							original_path=project_path,
							encoded_name=encoded_name,
							claude_json_data=proj_json_data,
							sessions=project_sessions,
							history_entries=history_entries,
						)
					)

	return data
