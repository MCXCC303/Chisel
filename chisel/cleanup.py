"""清理模块：删除无效路径的历史记录."""

from __future__ import annotations

import shutil
from pathlib import Path

from .models import ClaudeData, ProjectEntry
from .utils import safe_read_json, safe_read_jsonl, safe_write_json, safe_write_jsonl

def find_orphan_projects(data: ClaudeData) -> list[ProjectEntry]:
	"""查找项目目录已不存在的历史记录."""
	orphans = []
	for proj in data.projects:
		p = Path(proj.original_path)
		if not p.exists():
			orphans.append(proj)
	return orphans

def delete_sessions(
		data: ClaudeData,
		selected_uuids: set[str],
		claude_dir: Path,
		claude_json_path: Path,
		dry_run: bool = False,
) -> dict:
	"""删除指定会话的所有历史记录。

	Returns:
		操作报告
	"""
	report = {
		"dry_run": dry_run,
		"sessions_deleted": 0,
		"file_history_deleted": 0,
		"tasks_deleted": 0,
		"history_entries_removed": 0,
		"errors": [],
	}

	if dry_run:
		report["sessions_deleted"] = len(selected_uuids)
		for uuid in selected_uuids:
			fh = claude_dir / "file-history" / uuid
			if fh.exists():
				report["file_history_deleted"] += 1
			tk = claude_dir / "tasks" / uuid
			if tk.exists():
				report["tasks_deleted"] += 1
		return report

	# 1. 删除会话 jsonl 文件
	projects_dir = claude_dir / "projects"
	proj_uuids_map: dict[str, set[str]] = {}
	if projects_dir.exists():
		for proj_dir in projects_dir.iterdir():
			if not proj_dir.is_dir():
				continue
			for jsonl_file in proj_dir.glob("*.jsonl"):
				if jsonl_file.stem in selected_uuids:
					try:
						jsonl_file.unlink()
						report["sessions_deleted"] += 1
					except OSError as e:
						report["errors"].append(f"Cannot delete {jsonl_file}: {e}")

	# 2. 删除 file-history
	fh_dir = claude_dir / "file-history"
	if fh_dir.exists():
		for uuid in selected_uuids:
			target = fh_dir / uuid
			if target.exists():
				try:
					shutil.rmtree(target)
					report["file_history_deleted"] += 1
				except OSError as e:
					report["errors"].append(f"Cannot delete {target}: {e}")

	# 3. 删除 tasks
	tasks_dir = claude_dir / "tasks"
	if tasks_dir.exists():
		for uuid in selected_uuids:
			target = tasks_dir / uuid
			if target.exists():
				try:
					shutil.rmtree(target)
					report["tasks_deleted"] += 1
				except OSError as e:
					report["errors"].append(f"Cannot delete {target}: {e}")

	# 4. 从 history.jsonl 中移除相关条目
	history_path = claude_dir / "history.jsonl"
	if history_path.exists():
		existing = safe_read_jsonl(history_path)
		kept = [e for e in existing if e.get("sessionId") not in selected_uuids]
		removed = len(existing) - len(kept)
		if removed > 0:
			safe_write_jsonl(history_path, kept)
			report["history_entries_removed"] = removed

	# 5. 清理空的 project 目录
	if projects_dir.exists():
		for proj_dir in list(projects_dir.iterdir()):
			if proj_dir.is_dir() and not any(proj_dir.glob("*.jsonl")):
				try:
					shutil.rmtree(proj_dir)
				except OSError:
					pass

	# 6. 更新 claude.json 中仍存在的项目信息
	#    删除会话后，移除对应项目的 lastSessionId 如果它已被删除
	claude_json = safe_read_json(claude_json_path)
	if "projects" in claude_json:
		for path_key in list(claude_json["projects"].keys()):
			proj_data = claude_json["projects"][path_key]
			last_sid = proj_data.get("lastSessionId", "")
			if last_sid and last_sid in selected_uuids:
				# 清除被删除的 lastSessionId
				proj_data["lastSessionId"] = ""
				proj_data["lastSessionDate"] = ""
		safe_write_json(claude_json_path, claude_json)

	return report
