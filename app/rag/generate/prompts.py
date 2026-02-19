from pathlib import Path
def load_answer_template() -> str:
    return (Path(__file__).resolve().parents[3] / "prompts" / "answer_template.md").read_text(encoding="utf-8")
