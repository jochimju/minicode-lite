from __future__ import annotations

import json

import pytest

from minicode_lite.memory import MEMORY_DIR_NAME, MemoryManager


def test_add_memory_persists_and_can_be_reloaded(tmp_path) -> None:
    manager = MemoryManager(tmp_path)

    created = manager.add("编辑文件前创建 checkpoint", tags=["安全", "rewind"])
    reloaded = MemoryManager(tmp_path)

    assert (tmp_path / MEMORY_DIR_NAME / "memory.json").is_file()
    assert reloaded.entries == [created]


def test_search_returns_relevant_memories_in_score_order(tmp_path) -> None:
    manager = MemoryManager(tmp_path)
    manager.add("session 使用 JSON 持久化")
    strongest = manager.add("checkpoint 支持文件 rewind 恢复")
    manager.add("prompt 包含工具列表")

    results = manager.search("文件 checkpoint rewind")

    assert results == [strongest]


def test_chinese_short_query_can_match_memory(tmp_path) -> None:
    manager = MemoryManager(tmp_path)
    entry = manager.add("危险命令需要权限审批")

    assert manager.search("权限边界") == [entry]


def test_non_string_content_is_converted_to_stable_json(tmp_path) -> None:
    manager = MemoryManager(tmp_path)

    entry = manager.add({"stage": 10, "feature": "memory"})

    assert entry.content == '{"feature": "memory", "stage": 10}'


def test_empty_memory_content_is_rejected(tmp_path) -> None:
    manager = MemoryManager(tmp_path)

    with pytest.raises(ValueError, match="must not be empty"):
        manager.add("   ")


def test_empty_search_query_returns_no_matches(tmp_path) -> None:
    manager = MemoryManager(tmp_path)
    manager.add("some project fact")

    assert manager.search("   ") == []


def test_corrupted_memory_file_does_not_break_loading_or_search(tmp_path) -> None:
    memory_dir = tmp_path / MEMORY_DIR_NAME
    memory_dir.mkdir()
    (memory_dir / "memory.json").write_text("{broken", encoding="utf-8")

    manager = MemoryManager(tmp_path)

    assert manager.entries == []
    assert manager.search("anything") == []


def test_saved_memory_uses_explicit_schema_version(tmp_path) -> None:
    MemoryManager(tmp_path).add("schema contract")

    payload = json.loads(
        (tmp_path / MEMORY_DIR_NAME / "memory.json").read_text(encoding="utf-8")
    )

    assert payload["schema_version"] == 1
    assert payload["workspace"] == str(tmp_path.resolve())
