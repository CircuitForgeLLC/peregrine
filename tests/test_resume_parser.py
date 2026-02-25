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


def test_structure_resume_returns_dict():
    """structure_resume returns a dict with expected keys when LLM returns valid JSON."""
    raw_text = "Jane Doe\nSoftware Engineer at Acme 2020-2023"
    llm_response = '{"name": "Jane Doe", "experience": [{"company": "Acme", "title": "Engineer", "bullets": []}], "skills": [], "education": []}'

    with patch("scripts.resume_parser._llm_structure", return_value=llm_response):
        from scripts.resume_parser import structure_resume
        result = structure_resume(raw_text)

    assert isinstance(result, dict)
    assert "experience" in result
    assert isinstance(result["experience"], list)
    assert result["name"] == "Jane Doe"


def test_structure_resume_strips_markdown_fences():
    """structure_resume handles LLM output wrapped in ```json ... ``` fences."""
    raw_text = "Some resume"
    llm_response = '```json\n{"name": "Bob", "experience": []}\n```'

    with patch("scripts.resume_parser._llm_structure", return_value=llm_response):
        from scripts.resume_parser import structure_resume
        result = structure_resume(raw_text)

    assert result.get("name") == "Bob"


def test_structure_resume_invalid_json_returns_empty():
    """structure_resume returns {} on invalid JSON instead of crashing."""
    with patch("scripts.resume_parser._llm_structure", return_value="not json at all"):
        from scripts.resume_parser import structure_resume
        result = structure_resume("some text")

    assert isinstance(result, dict)
    assert result == {}


def test_structure_resume_llm_exception_returns_empty():
    """structure_resume returns {} when LLM raises an exception."""
    with patch("scripts.resume_parser._llm_structure", side_effect=Exception("LLM down")):
        from scripts.resume_parser import structure_resume
        result = structure_resume("some text")

    assert isinstance(result, dict)
    assert result == {}


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
