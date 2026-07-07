"""解包器：在新环境上解包并合并历史记录.

解包时读取占位符，接受用户指定的路径映射，
将所有占位符替换为真实路径后写入目标环境。
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from .utils import encode_project_path, safe_read_json, safe_read_jsonl, safe_write_json, safe_write_jsonl


def read_package_info(package_path: str | Path) -> dict:
    """读取迁移包的元数据（不解包）。

    Returns:
        metadata dict，包含 placeholders 信息
    """
    package_path = Path(package_path)
    with tarfile.open(package_path, "r:gz") as tar:
        try:
            member = tar.getmember("metadata.json")
            return json.loads(tar.extractfile(member).read().decode("utf-8"))
        except KeyError:
            return {}


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


def _build_replacements(placeholder_to_path: dict[str, str]) -> list[tuple[str, str]]:
    """构建替换列表: (占位符, 新路径)."""
    return [(ph, new_path) for ph, new_path in placeholder_to_path.items()]


def _str_replace(text: str, replacements: list[tuple[str, str]]) -> str:
    """对文本执行所有替换."""
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _bytes_replace(data: bytes, replacements: list[tuple[str, str]]) -> bytes:
    """对二进制内容执行所有替换."""
    return _str_replace(data.decode("utf-8", errors="replace"), replacements).encode("utf-8")


def unpack(
    package_path: str | Path,
    target_claude_dir: str | Path,
    target_claude_json_path: str | Path | None = None,
    placeholder_to_path: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict:
    """解包迁移包到目标环境。

    Args:
        package_path: 迁移包 .tar.gz 文件路径
        target_claude_dir: 目标 ~/.claude/ 目录
        target_claude_json_path: 目标 ~/.claude.json 路径
        placeholder_to_path: 占位符 → 新项目路径 的映射
        dry_run: 仅模拟，不实际写入

    Returns:
        操作报告 dict
    """
    package_path = Path(package_path)
    target_claude_dir = Path(target_claude_dir)
    if target_claude_json_path is None:
        target_claude_json_path = target_claude_dir.parent / ".claude.json"
    else:
        target_claude_json_path = Path(target_claude_json_path)

    if placeholder_to_path is None:
        placeholder_to_path = {}

    replacements = _build_replacements(placeholder_to_path)

    report = {
        "dry_run": dry_run,
        "projects_merged": 0,
        "sessions_copied": 0,
        "sessions_skipped": 0,
        "file_history_copied": 0,
        "tasks_copied": 0,
        "history_entries_appended": 0,
        "errors": [],
    }

    with tarfile.open(package_path, "r:gz") as tar:
        metadata = _load_json_from_tar(tar, "metadata.json")
        placeholders_meta = metadata.get("placeholders", {})

        for ph, ph_meta in placeholders_meta.items():
            new_path = placeholder_to_path.get(ph, ph)
            new_encoded = encode_project_path(new_path)
            index = ph_meta.get("index", 0)
            session_uuids = ph_meta.get("session_uuids", [])

            # --- 1. 复制 projects/<index>/<uuid>.jsonl ---
            proj_dest_dir = target_claude_dir / "projects" / new_encoded
            for uuid in session_uuids:
                src_path = f"projects/{index}/{uuid}.jsonl"
                dest_path = proj_dest_dir / f"{uuid}.jsonl"
                if dry_run:
                    report["sessions_copied" if not dest_path.exists() else "sessions_skipped"] += 1
                else:
                    try:
                        member = tar.getmember(src_path)
                        proj_dest_dir.mkdir(parents=True, exist_ok=True)
                        if not dest_path.exists():
                            content = tar.extractfile(member).read()
                            content = _bytes_replace(content, replacements)
                            dest_path.write_bytes(content)
                            report["sessions_copied"] += 1
                        else:
                            report["sessions_skipped"] += 1
                    except KeyError:
                        report["errors"].append(f"Missing in package: {src_path}")

            # --- 2. 复制 file-history/<uuid>/ ---
            fh_entries = _collect_tar_entries(tar, "file-history/")
            for uuid in session_uuids:
                prefix = f"file-history/{uuid}/"
                for member_name in fh_entries:
                    if member_name.startswith(prefix) and not member_name.endswith("/"):
                        rel_path = member_name[len("file-history/"):]
                        dest_path = target_claude_dir / "file-history" / rel_path
                        if dry_run:
                            if not dest_path.exists():
                                report["file_history_copied"] += 1
                        else:
                            if not dest_path.exists():
                                dest_path.parent.mkdir(parents=True, exist_ok=True)
                                content = tar.extractfile(tar.getmember(member_name)).read()
                                content = _bytes_replace(content, replacements)
                                dest_path.write_bytes(content)
                                report["file_history_copied"] += 1

            # --- 3. 复制 tasks/<uuid>/ ---
            task_entries = _collect_tar_entries(tar, "tasks/")
            for uuid in session_uuids:
                prefix = f"tasks/{uuid}/"
                for member_name in task_entries:
                    if member_name.startswith(prefix) and not member_name.endswith("/"):
                        rel_path = member_name[len("tasks/"):]
                        dest_path = target_claude_dir / "tasks" / rel_path
                        if dry_run:
                            if not dest_path.exists():
                                report["tasks_copied"] += 1
                        else:
                            if not dest_path.exists():
                                dest_path.parent.mkdir(parents=True, exist_ok=True)
                                content = tar.extractfile(tar.getmember(member_name)).read()
                                dest_path.write_bytes(content)
                                report["tasks_copied"] += 1

            # --- 4. 合并 claude.json ---
            if not dry_run:
                partial_json = _load_json_from_tar(tar, "claude.json.partial")
                if ph in partial_json.get("projects", {}):
                    target_json = safe_read_json(target_claude_json_path)
                    if "projects" not in target_json:
                        target_json["projects"] = {}
                    if new_path not in target_json["projects"]:
                        target_json["projects"][new_path] = {}

                    # 替换占位符后合并
                    raw_data = json.dumps(partial_json["projects"][ph], ensure_ascii=False)
                    raw_data = _str_replace(raw_data, replacements)
                    proj_data = json.loads(raw_data)
                    target_json["projects"][new_path].update(proj_data)
                    safe_write_json(target_claude_json_path, target_json)
                    report["projects_merged"] += 1

            # --- 5. 合并 history.jsonl ---
            if not dry_run:
                partial_history = _load_jsonl_from_tar(tar, "history.jsonl.partial")
                history_dest = target_claude_dir / "history.jsonl"
                existing_history = safe_read_jsonl(history_dest)
                existing_keys = {
                    (e.get("timestamp"), e.get("sessionId"), e.get("display"))
                    for e in existing_history
                }

                new_entries = []
                for entry in partial_history:
                    if entry.get("project") == ph:
                        entry["project"] = new_path
                    # 对其他字段也做替换
                    raw = json.dumps(entry, ensure_ascii=False)
                    raw = _str_replace(raw, replacements)
                    entry = json.loads(raw)
                    key = (entry.get("timestamp"), entry.get("sessionId"), entry.get("display"))
                    if key not in existing_keys:
                        new_entries.append(entry)
                        existing_keys.add(key)

                if new_entries:
                    all_entries = existing_history + new_entries
                    all_entries.sort(key=lambda e: e.get("timestamp", 0))
                    safe_write_jsonl(history_dest, all_entries)
                    report["history_entries_appended"] = len(new_entries)

        # --- 6. 合并全局设置 ---
        if not dry_run:
            for gf in ["settings.json", "stats-cache.json"]:
                try:
                    member = tar.getmember(gf)
                    dest = target_claude_dir / gf
                    if not dest.exists():
                        dest.write_bytes(tar.extractfile(member).read())
                except KeyError:
                    pass

    return report


def _collect_tar_entries(tar: tarfile.TarFile, prefix: str) -> list[str]:
    """收集 tar 中指定前缀下的所有成员名（缓存用）."""
    return [m.name for m in tar.getmembers() if m.name.startswith(prefix)]
