from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicode_lite.config import RuntimeConfig, load_runtime_config


CONFIG_ENV_NAMES = ("MINI_CODE_MODEL", "CUSTOM_API_BASE_URL", "CUSTOM_API_KEY")


def _clear_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CONFIG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_load_runtime_config_prefers_process_environment_over_dotenv_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    dotenv_path = tmp_path / ".env"
    settings_path.write_text(
        json.dumps(
            {
                "model": "settings-model",
                "base_url": "https://settings.example/v1/",
                "api_key": "settings-key",
            }
        ),
        encoding="utf-8",
    )
    dotenv_path.write_text(
        "# Local provider settings\n\n"
        "MINI_CODE_MODEL=dotenv-model\n"
        "CUSTOM_API_BASE_URL=https://dotenv.example/v1/\n"
        "CUSTOM_API_KEY=dotenv-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_CODE_MODEL", "environment-model")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "https://environment.example/v1/")
    monkeypatch.setenv("CUSTOM_API_KEY", "environment-key")

    config = load_runtime_config(settings_path=settings_path, dotenv_path=dotenv_path)

    assert config == RuntimeConfig(
        model="environment-model",
        base_url="https://environment.example/v1",
        api_key="environment-key",
        diagnostic="Qwen runtime configuration is complete.",
    )
    assert os.environ["MINI_CODE_MODEL"] == "environment-model"
    assert config.is_qwen_configured is True


def test_load_runtime_config_uses_json_settings_when_higher_sources_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_runtime_environment(monkeypatch)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "model": "settings-model",
                "base_url": "https://settings.example/v1/",
                "api_key": "settings-key",
            }
        ),
        encoding="utf-8",
    )

    config = load_runtime_config(
        settings_path=settings_path,
        dotenv_path=tmp_path / "missing.env",
    )

    assert config.model == "settings-model"
    assert config.base_url == "https://settings.example/v1"
    assert config.api_key == "settings-key"
    assert config.is_qwen_configured is True


def test_incomplete_runtime_config_reports_missing_variables_and_keeps_mock_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_runtime_environment(monkeypatch)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "MINI_CODE_MODEL=qwen3.7-max\n"
        "CUSTOM_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
        "CUSTOM_API_KEY=\n",
        encoding="utf-8",
    )

    config = load_runtime_config(dotenv_path=dotenv_path)

    assert config.is_qwen_configured is False
    assert "CUSTOM_API_KEY" in config.diagnostic
    assert "MINI_CODE_MODEL" not in config.diagnostic
    assert "CUSTOM_API_BASE_URL" not in config.diagnostic


@pytest.mark.parametrize("settings_content", ["{", "[]"])
def test_load_runtime_config_rejects_invalid_json_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings_content: str
) -> None:
    _clear_runtime_environment(monkeypatch)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(settings_content, encoding="utf-8")

    with pytest.raises(ValueError, match="settings"):
        load_runtime_config(settings_path=settings_path, dotenv_path=tmp_path / "missing.env")
