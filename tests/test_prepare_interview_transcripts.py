from pathlib import Path

from scripts.prepare_interview_transcripts import cleaned_transcript_markdown, write_cleaned_transcripts


def _docx_paragraph(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        for text in paragraphs
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}</w:body>
</w:document>""".encode("utf-8")


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    from zipfile import ZipFile

    with ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        zf.writestr("word/document.xml", _docx_paragraph(paragraphs))


def test_cleaned_transcript_markdown_removes_header_noise(tmp_path: Path):
    source = tmp_path / "Intervju Test-20260310_101010-Opptak av møte.docx"
    _write_minimal_docx(
        source,
        [
            "Intervju Test-20260310_101010-Opptak av møte",
            "10. mars 2026, 10:10a.m.",
            "47m 23s",
            "Pål Midtlien Danielsen startet transkripsjon",
            "Pål Midtlien Danielsen   0:03Hva tenker du?",
            "Svarperson   0:11Jeg tenker at helhet er viktig.",
            "1. Hvordan virker dette i praksis?",
        ],
    )

    out = cleaned_transcript_markdown(source)

    assert "# Intervju Test" in out
    assert "startet transkripsjon" not in out
    assert "47m 23s" not in out
    assert "**Svarperson:** Jeg tenker at helhet er viktig." in out
    assert "## Q1. Hvordan virker dette i praksis?" in out


def test_write_cleaned_transcripts_creates_markdown_files(tmp_path: Path):
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "cleaned"
    input_dir.mkdir()
    source = input_dir / "Intervju Glenn.docx"
    _write_minimal_docx(source, ["Intervju Glenn", "Glenn   0:03Hei"])

    written = write_cleaned_transcripts(input_dir, output_dir)

    assert len(written) == 1
    assert written[0].suffix == ".md"
    assert written[0].read_text(encoding="utf-8").startswith("# Intervju Glenn")
