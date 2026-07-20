from pathlib import Path


def test_architecture_notes_preserve_core_layers_and_comparison() -> None:
    notes = (Path(__file__).parents[1] / "ARCHITECTURE_NOTES.md").read_text(encoding="utf-8")

    required_sections = (
        "## 一句话结论",
        "## 1. 分层地图",
        "## 2. 核心路径逐模块对照",
        "## 3. 产品面与高级优化层",
        "## 5. 从真实项目迁移的测试思想",
        "## 6. 暂不复制的内容",
    )
    for section in required_sections:
        assert section in notes

    for module in ("agent_loop.py", "turn_kernel.py", "tooling.py", "permissions.py", "session.py", "readiness.py"):
        assert module in notes

    assert "entry -> model adapter -> agent loop -> tool registry" in notes
