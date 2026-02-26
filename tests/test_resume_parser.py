import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_extract_pdf_returns_string():
    """PDF extraction returns a string containing the expected text."""
    mock_page = MagicMock()
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
    assert result["name"] == "Jane Doe"
    assert result["email"] == "jane@example.com"


def test_structure_resume_empty_text_returns_error():
    """structure_resume returns empty dict + error message for empty input."""
    from scripts.resume_parser import structure_resume
    result, err = structure_resume("   ")

    assert result == {}
    assert err != ""


def test_parse_resume_contact_extraction():
    """parse_resume correctly extracts name, email, and phone from header block."""
    raw_text = (
        "Alice Smith\nalice.smith@email.com | (206) 555-9999\n\n"
        "Skills\nLeadership, Communication"
    )
    from scripts.resume_parser import parse_resume
    result, err = parse_resume(raw_text)

    assert err == ""
    assert result["name"] == "Alice Smith"
    assert result["email"] == "alice.smith@email.com"
    assert "555-9999" in result["phone"]


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
    assert result["name"] == "Bob Jones"
    assert "Project Management" in result["skills"]


def test_extract_pdf_empty_page_returns_string():
    """PDF with empty pages still returns a string (not None or crash)."""
    mock_page = MagicMock()
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
