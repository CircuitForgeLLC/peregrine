# Tier System

Peregrine uses a three-tier feature gate system defined in `app/wizard/tiers.py`.

---

## Tiers

```
free < paid < premium
```

| Tier | Description |
|------|-------------|
| `free` | Core discovery pipeline, resume matching, and basic UI — no LLM features |
| `paid` | All AI features: cover letters, research, email, integrations, calendar, notifications |
| `premium` | Adds fine-tuning and multi-user support |

---

## Feature Gate Table

Features listed here require a minimum tier. Features not in this table are available to all tiers (free by default).

### Wizard LLM generation

| Feature key | Minimum tier | Description |
|-------------|-------------|-------------|
| `llm_career_summary` | paid | LLM-assisted career summary generation in the wizard |
| `llm_expand_bullets` | paid | LLM expansion of resume bullet points |
| `llm_suggest_skills` | paid | LLM skill suggestions from resume content |
| `llm_voice_guidelines` | premium | LLM writing voice and tone guidelines |
| `llm_job_titles` | paid | LLM-suggested job title variations for search |
| `llm_keywords_blocklist` | paid | LLM-suggested blocklist keywords |
| `llm_mission_notes` | paid | LLM-generated mission alignment notes |

### App features

| Feature key | Minimum tier | Description |
|-------------|-------------|-------------|
| `company_research` | paid | Auto-generated company research briefs pre-interview |
| `interview_prep` | paid | Live reference sheet and practice Q&A during calls |
| `email_classifier` | paid | IMAP email sync with LLM classification |
| `survey_assistant` | paid | Culture-fit survey Q&A helper (text + screenshot) |
| `model_fine_tuning` | premium | Cover letter model fine-tuning on personal writing |
| `shared_cover_writer_model` | paid | Access to shared fine-tuned cover letter model |
| `multi_user` | premium | Multiple user profiles on one instance |

### Integrations (paid)

| Feature key | Minimum tier | Description |
|-------------|-------------|-------------|
| `notion_sync` | paid | Sync jobs to Notion database |
| `google_sheets_sync` | paid | Sync jobs to Google Sheets |
| `airtable_sync` | paid | Sync jobs to Airtable |
| `google_calendar_sync` | paid | Create interview events in Google Calendar |
| `apple_calendar_sync` | paid | Create interview events in Apple Calendar (CalDAV) |
| `slack_notifications` | paid | Pipeline event notifications via Slack |

### Free integrations (not gated)

The following integrations are free for all tiers and are not in the `FEATURES` dict:

- `google_drive_sync` — upload documents to Google Drive
- `dropbox_sync` — upload documents to Dropbox
- `onedrive_sync` — upload documents to OneDrive
- `mega_sync` — upload documents to MEGA
- `nextcloud_sync` — upload documents to Nextcloud
- `discord_notifications` — pipeline notifications via Discord webhook
- `home_assistant` — pipeline events to Home Assistant REST API

---

## API Reference

### `can_use(tier, feature) -> bool`

Returns `True` if the given tier has access to the feature.

```python
from app.wizard.tiers import can_use

can_use("free", "company_research")   # False
can_use("paid", "company_research")   # True
can_use("premium", "company_research") # True

can_use("free", "unknown_feature")    # True — ungated features return True
can_use("invalid", "company_research") # False — invalid tier string
```

### `tier_label(feature) -> str`

Returns a display badge string for locked features, or `""` if the feature is free or unknown.

```python
from app.wizard.tiers import tier_label

tier_label("company_research")  # "🔒 Paid"
tier_label("model_fine_tuning") # "⭐ Premium"
tier_label("job_discovery")     # ""  (ungated)
```

---

## Dev Tier Override

For local development and testing without a paid licence, set `dev_tier_override` in `config/user.yaml`:

```yaml
tier: free
dev_tier_override: premium    # overrides tier locally for testing
```

`UserProfile.tier` returns `dev_tier_override` when set, falling back to `tier` otherwise.

!!! warning
    `dev_tier_override` is for local development only. It has no effect on production deployments that validate licences server-side.

---

## Adding a New Feature Gate

1. Add the feature to `FEATURES` in `app/wizard/tiers.py`:

```python
FEATURES: dict[str, str] = {
    # ...existing entries...
    "my_new_feature": "paid",   # or "free" | "premium"
}
```

2. Guard the feature in the UI:

```python
from app.wizard.tiers import can_use, tier_label
from scripts.user_profile import UserProfile

user = UserProfile()
if can_use(user.tier, "my_new_feature"):
    # show the feature
    pass
else:
    st.info(f"My New Feature requires a {tier_label('my_new_feature').replace('🔒 ', '').replace('⭐ ', '')} plan.")
```

3. Add a test in `tests/test_tiers.py`:

```python
def test_my_new_feature_requires_paid():
    assert can_use("free", "my_new_feature") is False
    assert can_use("paid", "my_new_feature") is True
    assert can_use("premium", "my_new_feature") is True
```

---

## Future: Ultra Tier

An `ultra` tier is reserved for future use (e.g. enterprise SLA, dedicated inference). The tier ordering in `TIERS = ["free", "paid", "premium"]` can be extended without breaking `can_use()`, since it uses `list.index()` for comparison.
