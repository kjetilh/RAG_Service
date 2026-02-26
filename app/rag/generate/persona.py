from pathlib import Path

from app.settings import settings


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_prompt_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    return candidate if candidate.is_absolute() else (_repo_root() / candidate)


def load_persona() -> str:
    configured = (settings.system_persona_path or "").strip()
    path = _resolve_prompt_path(configured) if configured else (_repo_root() / "prompts" / "system_persona.md")
    if not path.exists():
        raise FileNotFoundError(f"System persona file not found: {path}")
    return path.read_text(encoding="utf-8")
