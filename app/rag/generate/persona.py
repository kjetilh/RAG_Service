from app.rag.generate.prompt_config_store import resolve_effective_paths, resolve_prompt_path


def load_persona() -> str:
    persona_path, _, _, _ = resolve_effective_paths()
    path = resolve_prompt_path(persona_path)
    if not path.exists():
        raise FileNotFoundError(f"System persona file not found: {path}")
    return path.read_text(encoding="utf-8")
