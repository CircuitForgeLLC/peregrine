# Tier System

Peregrine uses a three-tier feature gate system defined in `scripts/wizard/tiers.py`.

---

## Tiers

```
free < paid < premium
```

| Tier | Description |
|------|-------------|
| `free` | Core discovery pipeline, resume matching, basic UI. AI features unlock with BYOK. |
| `paid` | Managed cloud LLM (no key required), integrations, calendar, notifications |
| `premium` | Adds fine-tuning and multi-user support |

---

## BYOK — Bring Your Own Key

If you configure any LLM backend in `config/llm.yaml` — local (ollama, vllm) **or** an external API key (Anthropic, OpenAI, etc.) — **all pure LLM-call features unlock automatically**, regardless of your subscription tier.

The paid tier gives you access to CircuitForge's managed cloud inference. It does not gate your ability to use AI when you're providing the compute yourself.

Features that unlock with BYOK are listed in `BYOK_UNLOCKABLE` in `tiers.py`. Features that depend on CircuitForge-operated infrastructure (integrations, email classifier training, fine-tuned models) remain tier-gated.

---

## Feature Gate Table

Features listed here require a minimum tier. Features not in this table are available to all tiers (free by default).

### Wizard LLM generation

| Feature key | Minimum tier | BYOK unlocks? | Description |
|-------------|-------------|---------------|-------------|
| `llm_career_summary` | paid | ✅ yes | LLM-assisted career summary generation in the wizard |
| `llm_expand_bullets` | paid | ✅ yes | LLM expansion of resume bullet points |
| `llm_suggest_skills` | paid | ✅ yes | LLM skill suggestions from resume content |
| `llm_voice_guidelines` | premium | ✅ yes | LLM writing voice and tone guidelines |
| `llm_job_titles` | paid | ✅ yes | LLM-suggested job title variations for search |
| `llm_mission_notes` | paid | ✅ yes | LLM-generated mission alignment notes |
| `llm_keywords_blocklist` | paid | ❌ no | Orchestration pipeline over background keyword data |

### App features

| Feature key | Minimum tier | BYOK unlocks? | Description |
|-------------|-------------|---------------|-------------|
| `company_research` | paid | ✅ yes | Auto-generated company research briefs pre-interview |
| `interview_prep` | paid | ✅ yes | Live reference sheet and practice Q&A during calls |
| `survey_assistant` | paid | ✅ yes | Culture-fit survey Q&A helper (text + screenshot) |
| `email_classifier` | paid | ❌ no | IMAP email sync with LLM classification (training pipeline) |
| `model_fine_tuning` | premium | ❌ no | Cover letter model fine-tuning on personal writing |
| `shared_cover_writer_model` | paid | ❌ no | Access to shared fine-tuned cover letter model (CF infra) |
| `multi_user` | premium | ❌ no | Multiple user profiles on one instance |

### Integrations

Integrations depend on CircuitForge-operated infrastructure and are **not** BYOK-unlockable.

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

### `can_use(tier, feature, has_byok=False) -> bool`

Returns `True` if the given tier has access to the feature. Pass `has_byok=has_configured_llm()` to apply BYOK unlock logic. Called from `dev-api.py` route handlers, e.g. `can_use(_get_effective_tier(), "model_fine_tuning")` on the cloud custom-model endpoint.

```python
from scripts.wizard.tiers import can_use, has_configured_llm

byok = has_configured_llm()

can_use("free", "company_research")               # False — no LLM configured
can_use("free", "company_research", has_byok=True) # True  — BYOK unlocks it
can_use("paid", "company_research")               # True

can_use("free", "notion_sync", has_byok=True)     # False — integration, not BYOK-unlockable
can_use("free", "unknown_feature")                # True  — ungated features return True
can_use("invalid", "company_research")            # False — invalid tier string
```

### `has_configured_llm(config_path=None) -> bool`

Returns `True` if at least one non-vision LLM backend is enabled in `config/llm.yaml`. Local backends (ollama, vllm) and external API keys both count.

```python
from scripts.wizard.tiers import has_configured_llm

has_configured_llm()  # True if any backend is enabled and not vision_service
```

### `tier_label(feature, has_byok=False) -> str`

Returns a display badge string for locked features, or `""` if the feature is free, unlocked, or BYOK-accessible.

```python
from scripts.wizard.tiers import tier_label

tier_label("company_research")                    # "🔒 Paid"
tier_label("company_research", has_byok=True)     # ""  (BYOK unlocks, no label shown)
tier_label("model_fine_tuning")                   # "⭐ Premium"
tier_label("notion_sync", has_byok=True)          # "🔒 Paid"  (BYOK doesn't unlock integrations)
tier_label("job_discovery")                       # ""  (ungated)
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

1. Add the feature to `FEATURES` in `scripts/wizard/tiers.py`. If it's a pure LLM call that should unlock with BYOK, also add it to `BYOK_UNLOCKABLE`:

```python
FEATURES: dict[str, str] = {
    # ...existing entries...
    "my_new_llm_feature": "paid",
}

BYOK_UNLOCKABLE: frozenset[str] = frozenset({
    # ...existing entries...
    "my_new_llm_feature",   # add here if it's a pure LLM call
})
```

2. Guard the feature server-side in the relevant `dev-api.py` route, passing `has_byok` where the feature is a pure LLM call:

```python
from scripts.wizard.tiers import can_use, has_configured_llm

if not can_use(_get_effective_tier(), "my_new_llm_feature", has_byok=has_configured_llm()):
    raise HTTPException(402, detail={"error": "tier_required", "min_tier": "paid"})
```

3. Guard the feature in the Vue UI too (`config.tier` from `useAppConfigStore()`), so it's disabled/hidden before the user ever hits the tier-gated endpoint — see the Custom Model field in [Settings — Custom Model](../user-guide/settings.md#custom-model-cloud-premium) for the current visible-but-disabled pattern.

4. Add tests in `tests/test_wizard_tiers.py` covering both the tier gate and BYOK unlock:

```python
def test_my_new_feature_requires_paid_without_byok():
    assert can_use("free", "my_new_llm_feature") is False
    assert can_use("paid", "my_new_llm_feature") is True

def test_my_new_feature_byok_unlocks():
    assert can_use("free", "my_new_llm_feature", has_byok=True) is True
```
