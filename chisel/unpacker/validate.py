"""包校验模块 —— 验证迁移包的完整性和兼容性."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

REQUIRED_METADATA_FIELDS = [
	"version",
	"chisel_version",
	"project_count",
	"session_count",
	"placeholders",
]

REQUIRED_PLACEHOLDER_FIELDS = [
	"index",
	"basename",
	"encoded_name",
	"original_path",
	"session_count",
	"session_uuids",
	"history_entry_count",
]

REQUIRED_STRUCTURE_ENTRIES = [
	"metadata.json",
	"claude.json.partial",
]

class PackageError:
	"""包校验错误."""

	def __init__(self, message: str):
		self.message = message

	def __str__(self):
		return self.message

def _check_version(pkg_version: str, current_version: str) -> list[PackageError]:
	errors = []
	if not pkg_version:
		errors.append(PackageError("缺少 chisel_version 字段"))
		return errors
	try:
		pkg_parts = [int(x) for x in pkg_version.split(".")]
		cur_parts = [int(x) for x in current_version.split(".")]
	except ValueError:
		errors.append(PackageError(f"版本号格式无效: {pkg_version}"))
		return errors
	if pkg_parts[0] != cur_parts[0]:
		errors.append(PackageError(
			f"包主版本 ({pkg_parts[0]}.x) 与当前 Chisel ({cur_parts[0]}.x) 不兼容，"
			f"请使用相同主版本的 Chisel 重新打包"
		))
	return errors

def validate_package(package_path: str | Path) -> list[PackageError]:
	"""校验迁移包的完整性和兼容性。

	Returns:
		错误列表，空列表表示通过校验
	"""
	from .. import __version__

	package_path = Path(package_path)
	if not package_path.exists():
		return [PackageError(f"文件不存在: {package_path}")]
	if package_path.suffix not in (".gz",) and not package_path.name.endswith(".tar.gz"):
		return [PackageError("文件格式不正确，需要 .tar.gz 文件")]

	errors: list[PackageError] = []

	try:
		with tarfile.open(package_path, "r:gz") as tar:
			# 1. 检查基本文件结构
			entries = {m.name for m in tar.getmembers()}
			for required in REQUIRED_STRUCTURE_ENTRIES:
				if required not in entries:
					errors.append(PackageError(f"缺少必要文件: {required}"))

			# 2. 校验 metadata.json 字段
			try:
				metadata = json.loads(
					tar.extractfile(tar.getmember("metadata.json")).read().decode("utf-8")
				)
			except (KeyError, json.JSONDecodeError) as e:
				errors.append(PackageError(f"metadata.json 无效: {e}"))
				return errors

			for field in REQUIRED_METADATA_FIELDS:
				if field not in metadata:
					errors.append(PackageError(f"metadata.json 缺少字段: {field}"))

			pkg_ver = metadata.get("chisel_version", "")
			errors.extend(_check_version(pkg_ver, __version__))

			# 3. 校验各占位符
			placeholders = metadata.get("placeholders", {})
			if not isinstance(placeholders, dict) or not placeholders:
				errors.append(PackageError("placeholders 为空或格式无效"))
			else:
				seen_indices = set()
				for ph, ph_meta in placeholders.items():
					if not isinstance(ph, str) or not ph.startswith("__CM_PROJECT_"):
						errors.append(PackageError(f"无效的占位符格式: {ph}"))
					if not isinstance(ph_meta, dict):
						errors.append(PackageError(f"占位符 {ph} 的元数据格式无效"))
						continue
					for field in REQUIRED_PLACEHOLDER_FIELDS:
						if field not in ph_meta:
							errors.append(PackageError(f"占位符 {ph} 缺少字段: {field}"))
					idx = ph_meta.get("index")
					if idx is not None and idx in seen_indices:
						errors.append(PackageError(f"占位符 index 重复: {idx}"))
					seen_indices.add(idx)

					project_dir = f"projects/{idx}"
					uuids = ph_meta.get("session_uuids", [])
					if not isinstance(uuids, list):
						errors.append(PackageError(f"占位符 {ph} 的 session_uuids 不是列表"))
						continue
					for uuid in uuids:
						jsonl_path = f"{project_dir}/{uuid}.jsonl"
						if jsonl_path not in entries:
							errors.append(PackageError(
								f"占位符 {ph} 引用的会话文件缺失: {uuid}.jsonl"
							))

			# 4. 检查 projects/ 目录是否存在且非空
			if not any(m.name.startswith("projects/") and not m.isdir() for m in tar.getmembers()):
				errors.append(PackageError("包中无会话数据文件"))

	except tarfile.ReadError as e:
		errors.append(PackageError(f"无法读取 tar 文件: {e}"))
	except Exception as e:
		errors.append(PackageError(f"校验过程异常: {e}"))

	return errors
