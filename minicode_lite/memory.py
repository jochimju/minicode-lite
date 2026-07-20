from __future__ import annotations

"""提供项目级持久记忆、关键词检索和 prompt 上下文格式化。"""

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


MEMORY_DIR_NAME = ".minicode-lite-memory"
MEMORY_FILE_NAME = "memory.json"
_WORD_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


@dataclass
class MemoryEntry:
    """表示一条可持久化的项目事实；时间字段用于稳定排序和后续演进。"""

    entry_id: str
    content: str
    created_at: float
    updated_at: float
    tags: list[str] = field(default_factory=list)


def _stringify_content(content: Any) -> str:
    """把结构化输入稳定转换为文本，并拒绝无法形成有效记忆的空内容。"""

    if isinstance(content, str):
        # 字符串只清理边界空白，不改写用户事实内部的格式。
        text = content.strip()
    else:
        try:
            # JSON 比普通 str(dict) 更稳定，也更适合以后迁移到结构化索引。
            text = json.dumps(content, ensure_ascii=False, sort_keys=True).strip()
        except (TypeError, ValueError):
            # 自定义对象不一定支持 JSON；最小版本允许用其文本表示保存，而不是静默丢失。
            text = str(content).strip()
    if not text:
        # 空记忆既无法检索也会污染 prompt，因此在进入持久化层前失败。
        raise ValueError("memory content must not be empty")
    return text


def _tokens(text: str) -> set[str]:
    """提取英文词、数字标识符和中文词，并补充中文双字片段以支持短查询。"""

    # 集合会自然消除重复词，避免同一个词重复出现就获得不合理高分。
    tokens: set[str] = set()
    for raw_token in _WORD_RE.findall(text.lower()):
        # 保留完整词支持精确命中；英文统一小写由上一步完成。
        tokens.add(raw_token)
        if all("\u4e00" <= char <= "\u9fff" for char in raw_token):
            # 中文没有天然空格；双字片段足以支撑本阶段可解释的模糊命中。
            tokens.update(raw_token[index : index + 2] for index in range(len(raw_token) - 1))
    return tokens


class MemoryManager:
    """管理单个 workspace 的项目记忆，不跨项目读取或写入数据。"""

    def __init__(self, workspace: str | Path, *, max_results: int = 5) -> None:
        # resolve 固化项目边界，使同一目录的相对路径和绝对路径共用一份记忆。
        self.workspace = Path(workspace).resolve()
        # 存储位置由 workspace 推导，调用方不能借 memory API 指向任意外部文件。
        self.memory_dir = self.workspace / MEMORY_DIR_NAME
        self.memory_file = self.memory_dir / MEMORY_FILE_NAME
        # 至少允许返回一条结果，避免错误配置让默认检索永久失效。
        self.max_results = max(1, max_results)
        # 构造时只读取已有文件，不因一次普通查询创建项目垃圾目录。
        self.entries = self._load()

    def _load(self) -> list[MemoryEntry]:
        """加载格式正确的记忆；缺失或损坏文件按空记忆处理，保证主流程可继续。"""

        if not self.memory_file.is_file():
            # 首次使用项目时没有 memory 文件属于正常状态，不创建目录也不报错。
            return []
        try:
            # 一次性解析完整快照，后续所有校验都基于结构化对象而非字符串拼接。
            payload = json.loads(self.memory_file.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1 or not isinstance(payload.get("entries"), list):
                # 未知 schema 不能按当前数据类猜测读取，否则可能静默误解旧数据。
                return []
            entries: list[MemoryEntry] = []
            for item in payload["entries"]:
                if not isinstance(item, dict):
                    return []
                raw_tags = item.get("tags", [])
                if not isinstance(raw_tags, list):
                    return []
                entry = MemoryEntry(
                    entry_id=str(item["entry_id"]),
                    content=str(item["content"]),
                    created_at=float(item["created_at"]),
                    updated_at=float(item["updated_at"]),
                    tags=[str(tag) for tag in raw_tags],
                )
                if not entry.content.strip():
                    return []
                # 只有整条记录完成类型转换和内容检查后才进入可用集合。
                entries.append(entry)
            return entries
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            # 阶段 10 暂不自动修复损坏文件；返回空集合比把异常扩散到 agent loop 更安全。
            return []

    def _save(self) -> Path:
        """原子保存当前记忆快照，避免进程中断留下半个 JSON 文件。"""

        # 第一次真正写入时才创建隐藏目录，普通查询保持工作区不变。
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "workspace": str(self.workspace),
            "entries": [asdict(entry) for entry in self.entries],
        }
        # 临时文件和目标位于同一目录，replace 能以单次替换发布完整快照。
        temporary = self.memory_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.memory_file)
        return self.memory_file

    def add(self, content: Any, *, tags: list[str] | None = None) -> MemoryEntry:
        """规范化并持久化一条记忆，返回带稳定 ID 和时间戳的条目。"""

        # 内容和标签在创建数据对象前统一规范化，持久化文件不保存混合类型。
        text = _stringify_content(content)
        normalized_tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
        # 同一个 now 同时作为创建和更新时间，表达该条目尚未经历更新。
        now = time.time()
        entry = MemoryEntry(
            entry_id=uuid.uuid4().hex[:12],
            content=text,
            created_at=now,
            updated_at=now,
            tags=normalized_tags,
        )
        # 先更新内存列表，再由 _save 发布包含新条目的完整快照。
        self.entries.append(entry)
        self._save()
        return entry

    def search(self, query: Any, *, limit: int | None = None) -> list[MemoryEntry]:
        """按关键词重合度返回相关记忆；零关键词或零命中都返回空列表。"""

        if isinstance(query, str) and not query.strip():
            return []
        # 查询与记忆内容共用规范化规则，保证数字或结构化查询也有确定行为。
        query_text = _stringify_content(query)
        query_tokens = _tokens(query_text)
        if not query_tokens:
            return []
        # 元组同时保存相关度、新旧顺序和原条目，排序后无需再次查表。
        scored: list[tuple[int, float, MemoryEntry]] = []
        lowered_query = query_text.lower()
        for entry in self.entries:
            searchable_text = " ".join([entry.content, *entry.tags])
            overlap = query_tokens & _tokens(searchable_text)
            if not overlap:
                continue
            # 完整短语命中优先，其次按关键词数量，最后让新记忆在同分时靠前。
            phrase_bonus = 1 if lowered_query in searchable_text.lower() else 0
            scored.append((len(overlap) + phrase_bonus, entry.updated_at, entry))
        # 先按相关度、再按更新时间倒序，保证同一输入得到可预测顺序。
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        result_limit = self.max_results if limit is None else max(0, limit)
        return [item[2] for item in scored[:result_limit]]

    def get_context(self, query: Any, *, limit: int | None = None) -> str:
        """把检索结果格式化成紧凑、可直接注入 system prompt 的上下文。"""

        # 格式化层只消费检索结果，不重复实现相关度或截断策略。
        matches = self.search(query, limit=limit)
        return "\n".join(f"- {entry.content}" for entry in matches)
