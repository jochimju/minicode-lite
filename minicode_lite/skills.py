from __future__ import annotations

"""发现和读取项目技能；技能是带有 ``SKILL.md`` 的普通目录。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SkillSummary:
    """供列表展示的技能元数据，不携带完整正文。"""

    name: str  # 目录名也是模型调用 load_skill 时使用的稳定标识。
    description: str  # 简短说明用于 prompt 列表，避免提前加载完整正文。
    path: str  # 保留来源文件位置，便于诊断发现结果。
    source: str  # 区分 project、user 和兼容目录，并表达覆盖优先级。


@dataclass(frozen=True, slots=True)
class LoadedSkill(SkillSummary):
    """技能元数据加上按需读取的 Markdown 正文。"""

    content: str  # 只有按需加载阶段才携带完整技能指令。


def extract_description(markdown: str) -> str:
    """取正文第一行非标题文字，避免把整份技能提示塞进发现列表。"""

    for block in markdown.replace("\r\n", "\n").split("\n\n"):
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line.replace("`", "")
    return "No description provided."


def _roots(cwd: str | Path, home: Path | None = None) -> list[tuple[Path, str]]:
    """按覆盖优先级返回受支持的技能根目录。"""

    # 注入 home 让测试不读取开发机真实用户技能，生产调用则使用当前用户目录。
    base, user_home = Path(cwd), (Path.home() if home is None else home)
    return [
        (base / ".mini-code" / "skills", "project"),
        (user_home / ".mini-code" / "skills", "user"),
        (base / ".claude" / "skills", "compat_project"),
        (user_home / ".claude" / "skills", "compat_user"),
    ]


def _read_dirs(root: Path, source: str) -> list[LoadedSkill]:
    """读取一个来源；权限错误、断开的链接和非目录都安全跳过。"""

    # 根目录不存在是正常的“没有技能”状态，而不是运行错误。
    if not root.is_dir():
        return []
    result: list[LoadedSkill] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return []
    for entry in entries:
        try:
            skill_file = entry / "SKILL.md"
            if not entry.is_dir() or not skill_file.is_file():
                continue
            # resolve 后仍必须位于当前来源根内，阻止技能目录链接到任意外部文件。
            skill_file.resolve().relative_to(root.resolve())
            content = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            continue
        result.append(LoadedSkill(entry.name, extract_description(content), str(skill_file), source, content))
    return result


def discover_skills(cwd: str | Path, *, home: Path | None = None) -> list[SkillSummary]:
    """按项目优先、用户其次的顺序发现技能，并按名称去重。"""

    # dict 同时保存首次发现的高优先级版本和确定性的展示顺序。
    found: dict[str, LoadedSkill] = {}
    for root, source in _roots(cwd, home):
        for skill in _read_dirs(root, source):
            found.setdefault(skill.name, skill)
    return [SkillSummary(s.name, s.description, s.path, s.source) for s in found.values()]


def load_skill(cwd: str | Path, name: str, *, home: Path | None = None) -> LoadedSkill | None:
    """按名称读取单个技能；拒绝路径片段，防止借工具读取任意文件。"""

    # 只允许单级目录名；绝对路径、分隔符和父目录片段都不能成为读取入口。
    normalized = name.strip()
    if not normalized or Path(normalized).name != normalized or normalized in {".", ".."}:
        return None
    for root, source in _roots(cwd, home):
        skill_file = root / normalized / "SKILL.md"
        try:
            if skill_file.is_file():
                # 对符号链接做规范化边界检查，与发现阶段保持相同的安全语义。
                skill_file.resolve().relative_to(root.resolve())
                content = skill_file.read_text(encoding="utf-8")
                return LoadedSkill(normalized, extract_description(content), str(skill_file), source, content)
        except (OSError, UnicodeError, ValueError):
            continue
    return None


__all__ = ["LoadedSkill", "SkillSummary", "discover_skills", "extract_description", "load_skill"]
