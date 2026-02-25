# Integrations

Peregrine supports 13 optional integration connectors for job tracking, document storage, calendar sync, and notifications. Configure them in **Settings → Integrations** or during the first-run wizard (Step 7).

All integration credentials are stored in `config/integrations/<name>.yaml` (gitignored — never committed).

---

## Job Tracking

### Notion

**Tier:** Paid

Syncs approved and applied jobs to a Notion database. Peregrine creates or updates a Notion page per job with status, salary, company, URL, and cover letter text.

Required credentials: Notion integration token and database ID.

Configure in `config/integrations/notion.yaml`.

### Airtable

**Tier:** Paid

Syncs the job pipeline to an Airtable base. Each job maps to a row in your configured table.

Required credentials: Airtable personal access token, base ID, and table name.

### Google Sheets

**Tier:** Paid

Appends job data to a Google Sheet. Useful for sharing pipeline data or building custom dashboards.

Required credentials: Google service account JSON key file, spreadsheet ID, and sheet name.

---

## Document Storage

### Google Drive

**Tier:** Free

Uploads generated cover letters and exported PDFs to a Google Drive folder automatically when you export from the Apply Workspace.

Required credentials: Google service account JSON key file and target folder ID.

### Dropbox

**Tier:** Free

Uploads cover letters and PDFs to a Dropbox folder.

Required credentials: Dropbox access token and target folder path.

### OneDrive

**Tier:** Free

Uploads cover letters and PDFs to a OneDrive folder via the Microsoft Graph API.

Required credentials: Microsoft OAuth client ID, client secret, tenant ID, and target folder path.

### MEGA

**Tier:** Free

Uploads documents to MEGA cloud storage.

Required credentials: MEGA account email and password, target folder path.

### Nextcloud

**Tier:** Free

Uploads documents to a self-hosted Nextcloud instance via WebDAV.

Required credentials: Nextcloud server URL, username, password, and target folder path.

---

## Calendar

### Google Calendar

**Tier:** Paid

Creates calendar events for scheduled interviews. When you set an `interview_date` on a job in the kanban, Peregrine creates a Google Calendar event with a reminder.

Required credentials: Google service account JSON key file and calendar ID.

### Apple Calendar (CalDAV)

**Tier:** Paid

Creates calendar events on an Apple Calendar or any CalDAV-compatible server.

Required credentials: CalDAV server URL, username, and password. For iCloud, use an app-specific password.

---

## Notifications

### Slack

**Tier:** Paid

Sends notifications to a Slack channel for key pipeline events: new high-match jobs discovered, stage changes, and research completion.

Required credentials: Slack incoming webhook URL.

### Discord

**Tier:** Free

Sends notifications to a Discord channel via a webhook. Same events as Slack.

Required credentials: Discord webhook URL.

### Home Assistant

**Tier:** Free

Sends pipeline events to Home Assistant via the REST API. Useful for smart home dashboards or custom automation triggers.

Required credentials: Home Assistant base URL and long-lived access token.

---

## Integration Status

The Settings → Integrations tab shows the connection status of each integration:

| Status | Meaning |
|--------|---------|
| Connected | Credentials file exists and last test passed |
| Not configured | No credentials file found |
| Error | Credentials file exists but last test failed |

Click **Test** to re-verify the connection at any time.

---

## Adding a Custom Integration

See [Adding an Integration](../developer-guide/adding-integrations.md) in the developer guide.
