"""解包器内部辅助函数."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

def _load_json_from_tar(tar: tarfile.TarFile, name: str) -> dict:
	try:
		member = tar.getmember(name)
		return json.loads(tar.extractfile(member).read().decode("utf-8"))
	except (KeyError, json.JSONDecodeError):
		return {}

def _load_jsonl_from_tar(tar: tarfile.TarFile, name: str) -> list[dict]:
	try:
		member = tar.getmember(name)
		entries = []
		for line in tar.extractfile(member).read().decode("utf-8").splitlines():
			line = line.strip()
			if line:
				try:
					entries.append(json.loads(line))
				except json.JSONDecodeError:
					continue
		return entries
	except KeyError:
		return []

def _str_replace(text: str, replacements: list[tuple[str, str]]) -> str:
	for old, new in replacements:
		text = text.replace(old, new)
	return text

def _bytes_replace(data: bytes, replacements: list[tuple[str, str]]) -> bytes:
	return _str_replace(data.decode("utf-8", errors="replace"), replacements).encode("utf-8")

def _collect_tar_entries(tar: tarfile.TarFile, prefix: str) -> list[str]:
	return [m.name for m in tar.getmembers() if m.name.startswith(prefix)]

def _should_update_session(
		tar: tarfile.TarFile,
		src_path: str,
		dest_path: Path,
		replacements: list[tuple[str, str]],
) -> bool:
	"""判断是否应用包中会话覆盖目标文件。

	策略：仅当目标文件是源文件的严格前缀（即目标的所有行都能在
	源的对应位置找到，且源有更多行）时才更新。这意味着源是目标的
	延续版本。其他情况（长度相同、内容分叉、目标更长）均不覆盖。
	"""
	try:
		src_member = tar.getmember(src_path)
		src_content = tar.extractfile(src_member).read()
		src_content = _bytes_replace(src_content, replacements)
		src_lines = src_content.decode("utf-8").rstrip("\n").split("\n")

		dest_lines = dest_path.read_bytes().decode("utf-8").rstrip("\n").split("\n")

		if len(src_lines) <= len(dest_lines):
			return False

		for i, line in enumerate(dest_lines):
			if line != src_lines[i]:
				return False

		return True
	except Exception:
		return False
