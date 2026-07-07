"""扫描器：发现 ~/.claude 下的项目及其历史记录."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ClaudeData, ProjectEntry, SessionEntry
from .utils import decode_project_path, encode_project_path, safe_read_jsonl


def _build_path_map(projects_json: dict) -> dict[str, str]:
    """构建编码名到原始路径的映射。

    通过编码所有已知路径来建立反向查找，避免编码单向性的问题。
    """
    path_map: dict[str, str] = {}
    for original_path in projects_json:
        encoded = encode_project_path(original_path)
        path_map[encoded] = original_path
    return path_map


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

    # 构建编码名 → 原始路径的反向映射
    path_map = _build_path_map(projects_json)

    if projects_dir.exists():
        for encoded_dir in sorted(projects_dir.iterdir()):
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name

            # 优先通过编码映射查找原始路径，否则用解码兜底
            project_path = path_map.get(encoded_name)
            if project_path is None:
                project_path = decode_project_path(encoded_name)
                if project_path is None:
                    continue

            # 收集会话文件
            sessions = []
            for jsonl_file in sorted(encoded_dir.glob("*.jsonl")):
                uuid = jsonl_file.stem
                has_fh = (claude_dir / "file-history" / uuid).exists()
                has_tasks = (claude_dir / "tasks" / uuid).exists()
                sessions.append(
                    SessionEntry(
                        uuid=uuid,
                        has_file_history=has_fh,
                        has_tasks=has_tasks,
                        jsonl_path=jsonl_file,
                    )
                )

            proj_json_data = projects_json.get(project_path, {})

            # 从 history.jsonl 中提取该项目的条目
            history_entries = []
            history_path = claude_dir / "history.jsonl"
            if history_path.exists():
                all_history = safe_read_jsonl(history_path)
                history_entries = [
                    e for e in all_history
                    if e.get("project") == project_path
                ]

            data.projects.append(
                ProjectEntry(
                    original_path=project_path,
                    encoded_name=encoded_name,
                    claude_json_data=proj_json_data,
                    sessions=sessions,
                    history_entries=history_entries,
                )
            )

    return data
