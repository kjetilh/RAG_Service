from app.rag.generate.prompt_config_store import resolve_effective_paths, resolve_prompt_path


def load_answer_template() -> str:
    _, answer_path, _, _ = resolve_effective_paths()
    path = resolve_prompt_path(answer_path)
    if not path.exists():
        raise FileNotFoundError(f"Answer template file not found: {path}")
    return path.read_text(encoding="utf-8")
