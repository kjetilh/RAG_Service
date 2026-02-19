import re

def clean_text(text: str) -> str:
    # Postgres TEXT cannot contain NUL bytes (0x00). Remove defensively.
    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
