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


def test_collapse_letter_spacing_joins_spaced_headings_and_names():
    """Design-template PDFs letter-space headings and names ("E X P E R I E N C E"),
    which no section pattern matches."""
    from scripts.resume_parser import _collapse_letter_spacing

    assert _collapse_letter_spacing("E X P E R I E N C E") == "EXPERIENCE"
    assert _collapse_letter_spacing("C E R T I F I C A T I O N S") == "CERTIFICATIONS"
    assert _collapse_letter_spacing("N i k k i W i l s o n") == "Nikki Wilson"


def test_collapse_letter_spacing_leaves_ordinary_lines_alone():
    from scripts.resume_parser import _collapse_letter_spacing

    assert _collapse_letter_spacing("Served 40 guests nightly") == "Served 40 guests nightly"
    assert _collapse_letter_spacing("U S A") == "U S A"  # too short to be letter-spacing
    assert _collapse_letter_spacing("Plan A B C D rollout") == "Plan A B C D rollout"


def test_date_range_accepts_two_digit_years():
    """Month/two-digit-year ranges ("5/23 - 9/23") are common and were never matched,
    so a resume using them produced zero experience entries."""
    from scripts.resume_parser import _DATE_RANGE_RE

    m = _DATE_RANGE_RE.search("5/23 - 9/23")
    assert m and (m.group(1), m.group(2)) == ("5/23", "9/23")
    m = _DATE_RANGE_RE.search("Blackberry Soul Catering 2/25 - Present")
    assert m and m.group(1) == "2/25" and m.group(2).lower() == "present"
    assert _DATE_RANGE_RE.search("open 24/7 - 365 days a year") is None
    assert _DATE_RANGE_RE.search("Valid until 10/11/2027") is None


def test_parse_resume_reads_spaced_headings_and_two_digit_year_dates():
    from scripts.resume_parser import parse_resume

    text = (
        "N i k k i W i l s o n\n"
        "nikki@example.com\n"
        "E X P E R I E N C E\n"
        "Bartender | Preserve - Winters, CA | 5/23 - 9/23\n"
        "Server | Cedar's Corner | 7/24 - Present\n"
        "S K I L L S\n"
        "Cash handling\n"
    )
    struct, _ = parse_resume(text)

    assert (struct["name"], struct["surname"]) == ("Nikki", "Wilson")
    assert [e["title"] for e in struct["experience"]] == ["Bartender", "Server"]
    assert struct["experience"][0]["start_date"] == "5/23"
    assert "Cash handling" in struct["skills"]


def _two_column_pdf_with_header_across_the_gutter() -> bytes:
    """A big name that spans the gutter above two columns, and a left column whose
    lines end in a long token that runs almost up to the gutter. Word start positions
    are sparse there, which is what fooled a gap-between-word-starts gutter detector
    into splitting inside the left column."""
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 40)
    c.drawString(170, 730, "Nikki Wilson")
    c.setFont("Helvetica", 11)
    left = [
        ("Passionate friendly and", "customer-service-specialist"),
        ("Looking forward to", "learning-and-collaboration"),
        ("Calm under pressure", "cash-handling-experience"),
    ]
    for i, (short, long_token) in enumerate(left):
        c.drawString(40, 680 - i * 16, short)
        c.drawString(200, 680 - i * 16, long_token)
    for i, line in enumerate(["(334) 791-8613", "nikki@example.com", "Skills include opening", "and closing a busy bar."]):
        c.drawString(385, 680 - i * 16, line)
    c.save()
    return buf.getvalue()


def test_extract_pdf_does_not_cut_words_or_the_header_at_the_gutter():
    from scripts.resume_parser import extract_text_from_pdf

    text = extract_text_from_pdf(_two_column_pdf_with_header_across_the_gutter())

    assert "Nikki Wilson" in text
    for token in ("customer-service-specialist", "learning-and-collaboration", "cash-handling-experience"):
        assert token in text, f"{token} was cut at the gutter"
    assert "(334) 791-8613" in text
    assert text.index("cash-handling-experience") < text.index("(334) 791-8613")


def test_phone_pattern_accepts_spaces_around_the_hyphen():
    from scripts.resume_parser import _PHONE_RE

    assert _PHONE_RE.search("(334) 791 - 8613").group(0) == "(334) 791 - 8613"
    assert _PHONE_RE.search("334-791-8613")
    assert _PHONE_RE.search("(334) 791-8613")


def test_parse_resume_finds_contact_details_outside_the_header_block():
    """In a two-column template the phone and email sit at the top of the right
    column, which reads after the left column, so they are not in the header."""
    from scripts.resume_parser import parse_resume

    text = (
        "Jane Doe\n"
        "SUMMARY\n"
        "Friendly and reliable.\n"
        "EXPERIENCE\n"
        "Barista | Blue Bottle | 2019 - 2021\n"
        "CONTACT\n"
        "(334) 791 - 8613\n"
        "jane.doe@example.com\n"
    )
    struct, _ = parse_resume(text)

    assert struct["email"] == "jane.doe@example.com"
    assert struct["phone"] == "(334) 791 - 8613"


def test_parse_experience_reads_title_company_dates_on_separate_lines():
    from scripts.resume_parser import _parse_experience

    entries = _parse_experience([
        "Barista",
        "Blue Bottle Coffee - Oakland, CA",
        "2019 - 2021",
        "Made espresso drinks",
        "Shift Lead",
        "Philz Coffee - Berkeley, CA",
        "2021 - 2023",
    ])

    assert [(e["title"], e["company"]) for e in entries] == [
        ("Barista", "Blue Bottle Coffee - Oakland, CA"),
        ("Shift Lead", "Philz Coffee - Berkeley, CA"),
    ]
    assert entries[0]["bullets"] == ["Made espresso drinks"]


def test_parse_experience_shares_one_title_across_several_employers():
    """Some resumes list a title once, then several employers with their own dates."""
    from scripts.resume_parser import _parse_experience

    entries = _parse_experience([
        "Bartender/Server",
        "Preserve - Winters, CA",
        "5/23 - 9/23",
        "Back Door Bistro & Wine Bar - Vacaville, CA",
        "12/23 - 6/24",
        "Cedar's Corner Bar & Kitchen",
        "7/24 - 3/25",
        "Beertender",
        "Armadillo Music - Davis, CA",
        "6/22 - 2/25",
    ])

    assert [(e["title"], e["company"], e["start_date"]) for e in entries] == [
        ("Bartender/Server", "Preserve - Winters, CA", "5/23"),
        ("Bartender/Server", "Back Door Bistro & Wine Bar - Vacaville, CA", "12/23"),
        ("Bartender/Server", "Cedar's Corner Bar & Kitchen", "7/24"),
        ("Beertender", "Armadillo Music - Davis, CA", "6/22"),
    ]
    assert all(e["bullets"] == [] for e in entries)


def _narrow_gutter_pdf() -> bytes:
    """Two columns only ~16pt apart, as in compact design-template resumes."""
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 11)
    left = [
        "Managed high-volume shifts while maintaining accuracy and care",
        "Built rapport with repeat customers and provided real service",
        "Collaborated with team members to deliver great experiences",
        "Resolved concerns calmly and professionally for every guest.",
    ]
    right = ["Skills", "Exceptional attention to detail", "Fast and highly adaptable", "Clear confident communicator"]
    for i, line in enumerate(left):
        c.drawString(36, 700 - i * 16, line)
    for i, line in enumerate(right):
        c.drawString(351, 700 - i * 16, line)
    c.save()
    return buf.getvalue()


def test_extract_pdf_splits_columns_separated_by_a_narrow_gutter():
    import io

    import pdfplumber

    from scripts.resume_parser import _find_gutter, extract_text_from_pdf

    pdf_bytes = _narrow_gutter_pdf()
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        assert _find_gutter(pdf.pages[0]) is not None

    text = extract_text_from_pdf(pdf_bytes)
    assert text.index("for every guest.") < text.index("Exceptional attention")


def test_parse_experience_joins_a_company_wrapped_over_several_lines():
    """Bullets drawn as shapes have no marker, so the header block is found by working
    back from the date line to the last sentence-ending line."""
    from scripts.resume_parser import _parse_experience

    entries = _parse_experience([
        "Cashier/Food Runner",
        "Urban Plates - Davis, CA",
        "9/25 - Present",
        "Built lasting relationships with guests.",
        "Managed high-volume shifts.",
        "Bartender/Server",
        "Preserve, Back Door Bistro, Cedar's Corner,",
        "Blackberry Soul Catering - Winters, Vacaville,",
        "Bay Area, CA",
        "9/23 - 3/25",
        "Welcomed and assisted 100+ guests.",
    ])

    assert [(e["title"], e["start_date"]) for e in entries] == [
        ("Cashier/Food Runner", "9/25"),
        ("Bartender/Server", "9/23"),
    ]
    assert entries[0]["company"] == "Urban Plates - Davis, CA"
    assert entries[1]["company"] == (
        "Preserve, Back Door Bistro, Cedar's Corner, "
        "Blackberry Soul Catering - Winters, Vacaville, Bay Area, CA"
    )
    assert entries[0]["bullets"] == ["Built lasting relationships with guests.", "Managed high-volume shifts."]
    assert entries[1]["bullets"] == ["Welcomed and assisted 100+ guests."]


def test_parse_skills_keeps_sentence_style_skills_whole():
    """"Fast, efficient, and highly adaptable in dynamic environments" is one skill
    wrapped over lines, not four comma-separated keywords."""
    from scripts.resume_parser import _parse_skills

    skills = _parse_skills([
        "Exceptional attention to detail with",
        "strong observational skills",
        "Fast, efficient, and highly adaptable in",
        "dynamic environments",
        "Creative thinker with a critical,",
        "solutions-oriented mindset",
    ])

    assert skills == [
        "Exceptional attention to detail with strong observational skills",
        "Fast, efficient, and highly adaptable in dynamic environments",
        "Creative thinker with a critical, solutions-oriented mindset",
    ]


def test_parse_skills_still_splits_keyword_lists():
    from scripts.resume_parser import _parse_skills

    assert _parse_skills(["Python, SQL, Docker, Kubernetes", "AWS | Terraform"]) == [
        "Python", "SQL", "Docker", "Kubernetes", "AWS", "Terraform",
    ]


def test_parse_experience_does_not_mistake_a_company_name_for_a_sentence():
    """"BevMo!" and "Acme Inc." end like sentences but are company names."""
    from scripts.resume_parser import _parse_experience

    entries = _parse_experience([
        "Para/Teacher",
        "Fairfield School District",
        "10/19 - 6/23",
        "Cashier/Sales Associate",
        "BevMo!",
        "10/19 - 2/20",
        "Stock Clerk",
        "Acme Inc.",
        "3/20 - 5/21",
    ])

    assert [(e["title"], e["company"]) for e in entries] == [
        ("Para/Teacher", "Fairfield School District"),
        ("Cashier/Sales Associate", "BevMo!"),
        ("Stock Clerk", "Acme Inc."),
    ]
    assert all(e["bullets"] == [] for e in entries)


def test_parse_resume_keeps_contact_lines_out_of_the_last_job():
    """The phone and email lead the right column, which reads after the left one, so
    they arrive straight after the last job's dates."""
    from scripts.resume_parser import parse_resume

    text = (
        "Jane Doe\n"
        "EXPERIENCE\n"
        "Barista\n"
        "Blue Bottle Coffee - Oakland, CA\n"
        "1/18 - 7/19\n"
        "(334) 791 - 8613\n"
        "jane.doe@example.com\n"
        "SKILLS\n"
        "Cash handling\n"
    )
    struct, _ = parse_resume(text)

    assert struct["experience"][0]["bullets"] == []
    assert struct["email"] == "jane.doe@example.com"
    assert struct["phone"] == "(334) 791 - 8613"


def test_parse_resume_attaches_validity_dates_to_their_certification():
    from scripts.resume_parser import parse_resume

    text = (
        "Jane Doe\n"
        "CERTIFICATIONS\n"
        "ABC Responsible Beverage Service Certificate\n"
        "Valid until 3/14/2029\n"
        "CA Food Handler Card\n"
        "Valid until 10/11/2027\n"
    )
    struct, _ = parse_resume(text)

    assert struct["achievements"] == [
        "ABC Responsible Beverage Service Certificate, valid until 3/14/2029",
        "CA Food Handler Card, valid until 10/11/2027",
    ]
