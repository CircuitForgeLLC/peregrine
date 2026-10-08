import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_extract_pdf_returns_string():
    """PDF extraction returns a string containing the expected text."""
    mock_page = MagicMock()
    mock_page.bbox = (0, 0, 612, 792)
    mock_page.extract_text.return_value = "Jane Doe\nSoftware Engineer"
    mock_pdf_context = MagicMock()
    mock_pdf_context.pages = [mock_page]
    mock_pdf_cm = MagicMock()
    mock_pdf_cm.__enter__ = MagicMock(return_value=mock_pdf_context)
    mock_pdf_cm.__exit__ = MagicMock(return_value=False)

    with patch("scripts.resume_parser.pdfplumber") as mock_pdfplumber:
        mock_pdfplumber.open.return_value = mock_pdf_cm
        from scripts.resume_parser import extract_text_from_pdf
        result = extract_text_from_pdf(b"%PDF-fake")

    assert isinstance(result, str)
    assert "Jane Doe" in result


def test_extract_docx_returns_string():
    """DOCX extraction returns a string containing the expected text."""
    mock_para1 = MagicMock()
    mock_para1.text = "Alice Smith"
    mock_para2 = MagicMock()
    mock_para2.text = "Senior Developer"
    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para1, mock_para2]

    with patch("scripts.resume_parser.Document", return_value=mock_doc):
        from scripts.resume_parser import extract_text_from_docx
        result = extract_text_from_docx(b"PK fake docx bytes")

    assert isinstance(result, str)
    assert "Alice Smith" in result
    assert "Senior Developer" in result


def test_structure_resume_returns_tuple_with_keys():
    """structure_resume returns (dict, str) tuple with expected keys from plain text."""
    raw_text = (
        "Jane Doe\njane@example.com\n\n"
        "Experience\nSoftware Engineer | Acme Corp\nJan 2020 - Dec 2023\n• Built things\n\n"
        "Skills\nPython, SQL"
    )
    from scripts.resume_parser import structure_resume
    result, err = structure_resume(raw_text)

    assert err == ""
    assert isinstance(result, dict)
    assert "experience" in result
    assert isinstance(result["experience"], list)
    assert result["name"] == "Jane"
    assert result["surname"] == "Doe"
    assert result["email"] == "jane@example.com"


def test_structure_resume_empty_text_returns_error():
    """structure_resume returns empty dict + error message for empty input."""
    from scripts.resume_parser import structure_resume
    result, err = structure_resume("   ")

    assert result == {}
    assert err != ""


def test_parse_resume_contact_extraction():
    """parse_resume correctly extracts name, email, and phone from header block.

    name/surname are split -- the Resume Profile page has separate First
    Name / Last Name fields.
    """
    raw_text = (
        "Alice Smith\nalice.smith@email.com | (206) 555-9999\n\n"
        "Skills\nLeadership, Communication"
    )
    from scripts.resume_parser import parse_resume
    result, err = parse_resume(raw_text)

    assert err == ""
    assert result["name"] == "Alice"
    assert result["surname"] == "Smith"
    assert result["email"] == "alice.smith@email.com"
    assert "555-9999" in result["phone"]


def test_parse_resume_name_split_with_middle_name():
    """A three-part name puts everything after the first token into surname,
    matching how the rest of a name is conventionally treated as "last name"
    for job-application form-filling."""
    raw_text = "Mary Jane Watson\nmary@test.com\n\nSkills\nPhotography"
    from scripts.resume_parser import parse_resume
    result, err = parse_resume(raw_text)

    assert err == ""
    assert result["name"] == "Mary"
    assert result["surname"] == "Jane Watson"


def test_parse_resume_name_split_leaves_surname_blank_when_name_has_no_second_word():
    """When the name field itself is empty (e.g. the single-name-line
    heuristic didn't match -- a pre-existing limitation unrelated to this
    split fix), surname must not error, just stay blank too."""
    from scripts.resume_parser import _parse_header
    result = _parse_header(["", "cher@test.com"])

    assert result["name"] == ""
    assert result["surname"] == ""


def test_structure_resume_llm_failure_still_returns_result():
    """structure_resume returns usable result even when LLM career summary fails."""
    raw_text = (
        "Bob Jones\nbob@test.com\n\n"
        "Skills\nProject Management, Agile"
    )
    with patch("scripts.resume_parser._llm_career_summary", side_effect=Exception("LLM down")):
        from scripts.resume_parser import structure_resume
        result, err = structure_resume(raw_text)

    # Regex parse should still succeed even if LLM summary enhancement fails
    assert err == ""
    assert result["name"] == "Bob"
    assert result["surname"] == "Jones"
    assert "Project Management" in result["skills"]


def test_extract_pdf_empty_page_returns_string():
    """PDF with empty pages still returns a string (not None or crash)."""
    mock_page = MagicMock()
    mock_page.bbox = (0, 0, 612, 792)
    mock_page.extract_text.return_value = None  # pdfplumber can return None for empty pages
    mock_pdf_context = MagicMock()
    mock_pdf_context.pages = [mock_page]
    mock_pdf_cm = MagicMock()
    mock_pdf_cm.__enter__ = MagicMock(return_value=mock_pdf_context)
    mock_pdf_cm.__exit__ = MagicMock(return_value=False)

    with patch("scripts.resume_parser.pdfplumber") as mock_pdfplumber:
        mock_pdfplumber.open.return_value = mock_pdf_cm
        from scripts.resume_parser import extract_text_from_pdf
        result = extract_text_from_pdf(b"%PDF-empty")

    assert isinstance(result, str)


def _two_column_pdf_with_offset_page_box() -> bytes:
    """Two-column PDF whose page box is shifted off the origin, as Canva exports are."""
    import io

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 11)
    c.drawString(180, 740, "Jane Example")
    left = ["Profile", "Customer service specialist with five years of", "restaurant and retail experience, calm under pressure."]
    right = ["Skills", "Fast, efficient, and highly adaptable in busy", "dynamic environments with strong communication."]
    for i, line in enumerate(left):
        c.drawString(40, 690 - i * 16, line)
    for i, line in enumerate(right):
        c.drawString(360, 690 - i * 16, line)
    c.save()

    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
    page = writer.pages[0]
    page.mediabox.lower_left = (0, 8)
    page.mediabox.upper_right = (612, 800)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_extract_pdf_two_column_with_offset_page_box_does_not_raise():
    """Regression: a page box offset from the origin made the two-column crop
    fall outside the page and raise ValueError, failing the whole upload."""
    from scripts.resume_parser import extract_text_from_pdf

    text = extract_text_from_pdf(_two_column_pdf_with_offset_page_box())

    assert "Jane Example" in text
    assert "Customer service specialist" in text
    assert "dynamic environments" in text
    # Left column is read in full before the right column starts.
    assert text.index("restaurant and retail") < text.index("Skills")
