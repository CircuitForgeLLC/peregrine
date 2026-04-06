# Forgejo Feedback API — Schema & Bug Bot Setup

## API Endpoints Used

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List labels | GET | `/repos/{owner}/{repo}/labels` |
| Create label | POST | `/repos/{owner}/{repo}/labels` |
| Create issue | POST | `/repos/{owner}/{repo}/issues` |
| Upload attachment | POST | `/repos/{owner}/{repo}/issues/{index}/assets` |
| Post comment | POST | `/repos/{owner}/{repo}/issues/{index}/comments` |

Base URL: `https://git.opensourcesolarpunk.com/api/v1`

---

## Issue Creation Payload

```json
POST /repos/{owner}/{repo}/issues
{
  "title": "string",
  "body":  "markdown string",
  "labels": [1, 2, 3]   // array of label IDs (not names)
}
```

Response (201):
```json
{
  "number": 42,
  "html_url": "https://git.opensourcesolarpunk.com/pyr0ball/peregrine/issues/42"
}
```

---

## Issue Body Structure

The `build_issue_body()` function produces this markdown layout:

```markdown
## 🐛 Bug | ✨ Feature Request | 💬 Other

<user description>

### Reproduction Steps          ← bug type only, when repro provided

<repro steps>

### Context

- **page:** Home
- **version:** v0.2.5-61-ga6d787f   ← from `git describe`; "dev" inside Docker
- **tier:** free | paid | premium
- **llm_backend:** ollama | vllm | claude_code | ...
- **os:** Linux-6.8.0-65-generic-x86_64-with-glibc2.39
- **timestamp:** 2026-03-06T15:58:29Z

<details>
<summary>App Logs (last 100 lines)</summary>

```
... log content (PII masked) ...
```

</details>

### Recent Listings             ← only when include_diag = True

- [Title @ Company](url)

---
*Submitted by: Name <email>*   ← only when attribution consent checked
```

---

## Screenshot Attachment

Screenshots are uploaded as issue assets, then embedded inline via a follow-up comment:

```markdown
### Screenshot

![screenshot](https://git.opensourcesolarpunk.com/attachments/<uuid>)
```

This keeps the issue body clean and puts the screenshot in a distinct comment.

---

## Labels

| Label | Color | Applied when |
|-------|-------|-------------|
| `beta-feedback` | `#0075ca` | Always |
| `needs-triage` | `#e4e669` | Always |
| `bug` | `#d73a4a` | Type = Bug |
| `feature-request` | `#a2eeef` | Type = Feature Request |
| `question` | `#d876e3` | Type = Other |

Labels are looked up by name on each submission; missing ones are auto-created via `_ensure_labels()`.

---

## Bug Bot Account Setup

The token currently bundled in `.env` is pyr0ball's personal token. For beta distribution,
create a dedicated bot account so the token has limited scope and can be rotated independently.

### Why a bot account?

- Token gets bundled in beta testers' `.env` — shouldn't be tied to the repo owner's account
- Bot can be limited to issue write only (cannot push code, see private repos, etc.)
- Token rotation doesn't affect the owner's other integrations

### Steps (requires Forgejo admin panel — API admin access not available on this token)

1. **Create bot account** at `https://git.opensourcesolarpunk.com/-/admin/users/new`
   - Username: `peregrine-bot` (or `cf-bugbot`)
   - Email: a real address you control (e.g. `bot+peregrine@circuitforge.tech`)
   - Set a strong password (store in your password manager)
   - Check "Prohibit login" if you want a pure API-only account

2. **Add as collaborator** on `pyr0ball/peregrine`:
   - Settings → Collaborators → Add `peregrine-bot` with **Write** access
   - Write access is required to create labels; issue creation alone would need only Read+Comment

3. **Generate API token** (log in as the bot, or use admin impersonation):
   - User Settings → Applications → Generate New Token
   - Name: `peregrine-feedback`
   - Scopes: `issue` (write) — no repo code access needed
   - Copy the token — it won't be shown again

4. **Update environment**:
   ```
   FORGEJO_API_TOKEN=<new bot token>
   FORGEJO_REPO=pyr0ball/peregrine
   FORGEJO_API_URL=https://git.opensourcesolarpunk.com/api/v1
   ```
   Update both `.env` (dev machine) and any beta tester `.env` files.

5. **Verify** the bot can create issues:
   ```bash
   curl -s -X POST https://git.opensourcesolarpunk.com/api/v1/repos/pyr0ball/peregrine/issues \
     -H "Authorization: token <bot-token>" \
     -H "Content-Type: application/json" \
     -d '{"title":"[TEST] bot token check","body":"safe to close","labels":[]}'
   ```
   Expected: HTTP 201 with `number` and `html_url` in response.

### Future: Heimdall token management

Once Heimdall is live, the bot token should be served by the license server rather than
bundled in `.env`. The app fetches it at startup using the user's license key → token is
never stored on disk and can be rotated server-side. Track as a future Heimdall feature.
