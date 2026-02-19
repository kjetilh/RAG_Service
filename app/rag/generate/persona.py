from pathlib import Path
def load_persona() -> str:
    return (Path(__file__).resolve().parents[3] / "prompts" / "system_persona.md").read_text(encoding="utf-8")
