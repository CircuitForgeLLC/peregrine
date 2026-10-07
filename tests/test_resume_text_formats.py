"""Resume uploads accept plain text, Markdown, HTML and RTF as well as PDF, DOCX and ODT.

Legacy .doc and Apple .pages files are deliberately not supported (no reliable pure-Python
reader), they get a clear "export it as PDF or DOCX" message instead of a crash.
"""
import pytest
from fastapi.testclient import TestClient

from scripts import resume_parser
from scripts.db_migrate import migrate_db

RESUME_TEXT = (
    "Alex Rivera\n"
    "alex@example.com | 555-0100\n"
    "\n"
    "SUMMARY\n"
    "Senior support engineer who likes untangling hard problems.\n"
    "\n"
    "EXPERIENCE\n"
    "Support Engineer, Acme Corp\n"
    "2019 - 2024\n"
    "- Resolved escalations for enterprise customers\n"
    "\n"
    "EDUCATION\n"
    "BS Computer Science, State University\n"
    "\n"
    "SKILLS\n"
    "Python, SQL, customer communication\n"
)


# ── Extractors ───────────────────────────────────────────────────────────────

def test_plain_text_utf8():
    assert resume_parser.extract_text_from_text("Zoë Núñez".encode()) == "Zoë Núñez"


def test_plain_text_strips_a_byte_order_mark():
    assert resume_parser.extract_text_from_text(b"\xef\xbb\xbfAlex") == "Alex"


def test_plain_text_falls_back_to_windows_1252():
    assert resume_parser.extract_text_from_text("café".encode("cp1252")) == "café"


def test_plain_text_normalises_windows_line_endings():
    assert resume_parser.extract_text_from_text(b"one\r\ntwo\r\n") == "one\ntwo\n"


MARKDOWN_RESUME = (
    "# Alex Rivera\n\n"
    "alex@example.com | 555-0100\n\n"
    "## Summary\n\nSenior support engineer who likes untangling **hard** problems.\n\n"
    "## Experience\n\n"
    "### Support Engineer, Acme Corp\n\n"
    "*2019 - 2024*\n\n"
    "- Resolved escalations for [enterprise](https://example.com) customers\n"
    "- Wrote the runbook\n\n"
    "## Education\n\nBS Computer Science, State University\n\n"
    "## Skills\n\nPython, SQL, customer communication\n"
)


def test_markdown_syntax_is_stripped_to_readable_text():
    text = resume_parser.extract_text(MARKDOWN_RESUME.encode(), ".md")

    for marker in ("#", "**", "](", "*2019"):
        assert marker not in text, f"leftover markdown syntax {marker!r}"
    assert "Alex Rivera" in text
    assert "enterprise customers" in text
    assert "Experience" in text.splitlines()


def test_markdown_resume_parses_into_sections():
    text = resume_parser.extract_text(MARKDOWN_RESUME.encode(), ".md")

    result, err = resume_parser.parse_resume(text)

    assert not err
    assert result["experience"], "markdown headings should not hide the Experience section"
    assert result["skills"]
    assert result["education"]


def test_html_keeps_text_in_order_and_drops_scripts_and_styles():
    html = (
        b"<html><head><title>Resume</title><style>p{color:red}</style></head>"
        b"<body><h1>Alex Rivera</h1><script>alert('x')</script>"
        b"<p>Support Engineer</p><ul><li>Python</li><li>SQL</li></ul></body></html>"
    )

    text = resume_parser.extract_text_from_html(html)

    assert text.splitlines() == ["Alex Rivera", "Support Engineer", "Python", "SQL"]
    assert "alert" not in text
    assert "color" not in text


def test_html_inline_tags_do_not_split_a_sentence():
    html = b"<p>Led <b>12</b> engineers at <a href='#'>Acme</a>, a <span>fast-growing</span> startup</p>"

    assert resume_parser.extract_text_from_html(html) == "Led 12 engineers at Acme, a fast-growing startup"


def test_html_table_cells_and_line_breaks_become_separate_lines():
    html = b"<table><tr><td>Python</td><td>SQL</td></tr></table><p>one<br>two</p>"

    assert resume_parser.extract_text_from_html(html).splitlines() == ["Python", "SQL", "one", "two"]


def test_html_with_no_body_markup_still_returns_text():
    assert resume_parser.extract_text_from_html(b"Just some text") == "Just some text"


def test_rtf_returns_the_visible_words():
    rtf = rb"{\rtf1\ansi\deff0 {\fonttbl{\f0 Arial;}}\f0\fs24 Alex Rivera\par Support Engineer\par}"

    text = resume_parser.extract_text_from_rtf(rtf)

    assert "Alex Rivera" in text
    assert "Support Engineer" in text
    assert "fonttbl" not in text
    assert "\\" not in text


def test_dispatcher_routes_by_suffix_case_insensitively():
    assert resume_parser.extract_text(b"hello", ".TXT") == "hello"
    assert resume_parser.extract_text(b"# Heading\n\ntext", ".md").splitlines() == ["Heading", "text"]
    assert resume_parser.extract_text(b"<p>hi</p>", ".htm") == "hi"


@pytest.mark.parametrize("suffix", [".doc", ".pages", ".xyz", ""])
def test_dispatcher_refuses_unsupported_suffixes(suffix):
    with pytest.raises(ValueError):
        resume_parser.extract_text(b"data", suffix)


def test_supported_suffixes_are_exposed_for_the_api():
    assert set(resume_parser.SUPPORTED_SUFFIXES) == {
        ".pdf", ".docx", ".odt", ".rtf", ".html", ".htm", ".md", ".txt",
    }


# ── Upload endpoint, end to end with the real parser ─────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    (tmp_path / "config").mkdir()
    monkeypatch.setenv("STAGING_DB", str(db))
    migrate_db(db)
    import dev_api

    monkeypatch.setattr(
        dev_api, "_request_db",
        type("CV", (), {"get": lambda self: str(db), "set": lambda *a: None})(),
    )
    return TestClient(dev_api.app)


def _as_html(text: str) -> bytes:
    body = "".join(f"<p>{line}</p>" for line in text.splitlines())
    return f"<html><body>{body}</body></html>".encode()


def _as_rtf(text: str) -> bytes:
    return ("{\\rtf1\\ansi " + "\\par ".join(text.splitlines()) + "}").encode()


@pytest.mark.parametrize("filename,content", [
    ("resume.txt", RESUME_TEXT.encode()),
    ("resume.md", RESUME_TEXT.encode()),
    ("resume.html", _as_html(RESUME_TEXT)),
    ("resume.htm", _as_html(RESUME_TEXT)),
    ("resume.rtf", _as_rtf(RESUME_TEXT)),
])
def test_upload_accepts_text_based_formats(client, filename, content):
    resp = client.post(
        "/api/settings/resume/upload",
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True, body
    assert body["data"]["name"] == "Alex"
    assert body["data"]["email"] == "alex@example.com"


@pytest.mark.parametrize("filename", ["resume.doc", "resume.pages"])
def test_doc_and_pages_get_an_export_hint(client, filename):
    body = client.post(
        "/api/settings/resume/upload",
        files={"file": (filename, b"x", "application/octet-stream")},
    ).json()

    assert body["ok"] is False
    assert "PDF" in body["error"] and "DOCX" in body["error"]
    assert "export" in body["error"].lower() or "save as" in body["error"].lower()


def test_library_import_accepts_rtf_and_html(client):
    for filename, content in [("a.rtf", _as_rtf(RESUME_TEXT)), ("b.html", _as_html(RESUME_TEXT))]:
        resp = client.post(
            "/api/resumes/import",
            files={"file": (filename, content, "application/octet-stream")},
            data={"name": filename},
        )
        assert resp.status_code == 200, (filename, resp.text)
        assert "Alex Rivera" in resp.json()["text"]
