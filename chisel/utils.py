"""工具函数：路径编码、文件操作等."""

from __future__ import annotations

import re
from pathlib import Path


def encode_project_path(project_path: str) -> str:
    """将项目绝对路径编码为目录名。

    规则（与 Claude Code 一致）：
    - 起始 / → -
    - 后续 / → -
    - : → -
    - \\ → -
    - 空格 → -
    - 非 ASCII 字符 → _
    - 其余保留
    """
    result = project_path

    # 处理起始 /
    if result.startswith("/"):
        result = "-" + result[1:]

    # 替换需要映射的字符
    result = result.replace(":", "-")
    result = result.replace("\\", "-")
    result = result.replace("/", "-")
    result = result.replace(" ", "-")

    # 非 ASCII 字符转为 _
    result = re.sub(r"[^\x00-\x7F]", "_", result)

    return result


def decode_project_path(encoded_name: str) -> str | None:
    """从编码名尝试恢复原始路径。

    由于编码是单向的（多个字符映射到同一字符），只能尽力还原。
    返回的路径以 / 开头，分隔符为 /。
    """
    # 将首个 - 还原为 /
    if encoded_name.startswith("-"):
        decoded = "/" + encoded_name[1:]
    else:
        decoded = "/" + encoded_name

    # 将 - 还原为 /
    decoded = decoded.replace("-", "/")

    # 清理可能的连续 /
    decoded = re.sub(r"/+", "/", decoded)

    return decoded


def verify_encoding(project_path: str, encoded_name: str) -> bool:
    """验证路径编码是否正确（用于测试）."""
    return encode_project_path(project_path) == encoded_name


def safe_read_jsonl(path: Path) -> list[dict]:
    """安全读取 JSONL 文件，跳过损坏的行."""
    entries = []
    if not path.exists():
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(__import__("json").loads(line))
            except Exception:
                continue
    return entries


def safe_write_jsonl(path: Path, entries: list[dict]) -> None:
    """写入 JSONL 文件."""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def safe_read_json(path: Path) -> dict:
    """安全读取 JSON 文件."""
    import json
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_write_json(path: Path, data: dict) -> None:
    """写入 JSON 文件."""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
