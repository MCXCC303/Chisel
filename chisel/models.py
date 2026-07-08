"""数据模型定义."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class SessionEntry:
	"""单个会话的引用信息."""

	uuid: str
	has_file_history: bool = False
	has_tasks: bool = False
	jsonl_path: Path | None = None

@dataclass
class ProjectEntry:
	"""一个项目的完整迁移数据."""

	original_path: str  # 原始绝对路径，如 /home/alice/Programme/Java/Salicin
	encoded_name: str  # 编码后的目录名，如 -home-alice-Programme-Java-Salicin
	claude_json_data: dict[str, Any]  # claude.json 中该项目的条目
	sessions: list[SessionEntry] = field(default_factory=list)
	history_entries: list[dict[str, Any]] = field(default_factory=list)  # history.jsonl 中属于该项目的条目

	@property
	def session_uuids(self) -> list[str]:
		return [s.uuid for s in self.sessions]

@dataclass
class ClaudeData:
	"""Claude Code 全局数据的完整视图."""

	claude_dir: Path  # ~/.claude/ 目录
	claude_json_path: Path  # ~/.claude.json 路径
	claude_json: dict[str, Any] = field(default_factory=dict)  # 完整的 claude.json 内容
	projects: list[ProjectEntry] = field(default_factory=list)

	@classmethod
	def load(cls, claude_dir: Path, claude_json_path: Path) -> ClaudeData:
		"""从目录加载数据."""
		data = cls(claude_dir=claude_dir, claude_json_path=claude_json_path)
		if claude_json_path.exists():
			with open(claude_json_path, "r", encoding="utf-8") as f:
				data.claude_json = json.load(f)
		return data

@dataclass
class PathMapping:
	"""路径映射关系."""

	old_path: str
	new_path: str
	old_encoded: str
	new_encoded: str
