"""Config helpers — read a .env-style file, no dependency on python-dotenv."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def base_dir() -> Path:
    return Path(os.environ.get("TGFLOW_HOME", Path(__file__).resolve().parent.parent))


def env_path() -> Path:
    return base_dir() / ".env"


def read_env(path: Path | None = None) -> dict[str, str]:
    """Parse a KEY=VALUE file into a dict. Unknown keys are preserved."""
    path = path or env_path()
    config: dict[str, str] = {}
    if not path.exists():
        return config
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()
    return config


def write_env(config: dict[str, Any], path: Path | None = None) -> None:
    path = path or env_path()
    merged = dict(read_env(path))
    merged.update({k: v for k, v in config.items() if v is not None})
    lines = [f"{k}={v}\n" for k, v in merged.items()]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def boolish(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [c.strip().lstrip("@") for c in raw.split(",") if c.strip()]
