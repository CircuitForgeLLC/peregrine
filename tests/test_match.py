import pytest
from unittest.mock import patch, MagicMock


def test_extract_job_description_from_url():
    """extract_job_description fetches and returns visible text from a URL."""
    from scripts.match import extract_job_description

    with patch("scripts.match.requests.get") as mock_get:
        mock_get.return_value.text = "<html><body><p>We need a CSM with Salesforce.</p></body></html>"
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_job_description("https://example.com/job/123")

    assert "CSM" in result
    assert "Salesforce" in result


def test_score_is_between_0_and_100():
    """match_score returns a float in [0, 100] and a list of keyword gaps."""
    from scripts.match import match_score

    score, gaps = match_score(
        resume_text="Customer Success Manager with Salesforce experience",
        job_text="Looking for a Customer Success Manager who knows Salesforce and Gainsight",
    )
    assert 0 <= score <= 100
    assert isinstance(gaps, list)


def test_write_score_to_notion():
    """write_match_to_notion updates the Notion page with score and gaps."""
    from scripts.match import write_match_to_notion

    mock_notion = MagicMock()

    SAMPLE_FM = {
        "match_score": "Match Score",
        "keyword_gaps": "Keyword Gaps",
    }

    write_match_to_notion(mock_notion, "page-id-abc", 85.5, ["Gainsight", "Churnzero"], SAMPLE_FM)

    mock_notion.pages.update.assert_called_once()
    call_kwargs = mock_notion.pages.update.call_args[1]
    assert call_kwargs["page_id"] == "page-id-abc"
    score_val = call_kwargs["properties"]["Match Score"]["number"]
    assert score_val == 85.5
