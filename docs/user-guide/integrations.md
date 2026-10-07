# Integrations

Integrations connect Peregrine to other tools you already use, so your jobs, cover letters, and interview dates follow you there.

Every integration is optional. Peregrine works fine without any of them.

## What you will do here

1. Open **Settings** from the sidebar, then click **Connections**. You will see **Email (IMAP)** at the top and an **Integrations** list below it.
2. Find the service you want. Each one shows a **Connected** or **Disconnected** badge.
3. Fill in the fields for that service and click **Connect**. You can click **Test** first to check your details.
4. You will see **✓ OK** when it works, or **✗** with a short reason when it does not. The badge changes to **Connected**.

To remove a service, click **Disconnect** on its card.

Peregrine also offers **Connections** during first-time setup. You can skip it and come back later. See [Settings](settings.md) for the rest of the settings pages.

!!! note "Free and Paid"
    Document storage and Discord are Free. Job tracking, calendars, and Slack are Paid. Integrations stay on the Paid plan even if you connect your own LLM key (bring your own key, or BYOK), because they run on infrastructure CircuitForge operates.

A locked service shows **Requires paid** and an upgrade note instead of the connect fields.

---

## Job tracking

### Notion

**Paid.** Keeps a Notion database up to date with the jobs you approve and apply to. Each job gets a page with its status, salary, company, link, and cover letter text.

1. In Notion, create an integration and copy its secret token.
2. Share your jobs database with that integration, then copy the database ID from its address.
3. In Peregrine, enter the **Integration Token** and the **Database ID**.
4. Click **Test**, then **Connect**.

### Airtable

**Paid.** Syncs your job pipeline to an Airtable base. Each job becomes a row in the table you choose.

1. In Airtable, create a personal access token.
2. Note your base ID and the name of the table.
3. In Peregrine, enter the **Personal Access Token**, **Base ID**, and **Table name**.
4. Click **Test**, then **Connect**.

### Google Sheets

**Paid.** Adds your job data to a Google Sheet. Handy if you want to share your progress or build your own charts.

1. Prepare a Google service account and share your sheet with it. A service account is a robot login that Google gives to apps.
2. Copy the spreadsheet ID from the sheet's address.
3. In Peregrine, enter the **Spreadsheet ID**, **Sheet name**, and the **Service Account JSON path**.
4. Click **Test**, then **Connect**.

---

## Document storage

Document storage services save your finished cover letters and exported PDFs into a folder you choose. All five are Free.

### Google Drive

Saves cover letters and PDFs to a Google Drive folder.

1. Prepare a Google service account and share your target folder with it.
2. Copy the folder ID from the folder's address.
3. Enter the **Folder ID** and the **Service Account JSON path**.
4. Click **Test**, then **Connect**.

### Dropbox

Saves cover letters and PDFs to a Dropbox folder.

1. Create an access token in the Dropbox developer console.
2. Enter the **Access Token** and the **Folder path**.
3. Click **Test**, then **Connect**.

### OneDrive

Saves cover letters and PDFs to a OneDrive folder.

1. Register an app in your Microsoft account to get a client ID and secret.
2. Enter the **Application (client) ID**, **Client secret**, and **Folder path**.
3. Click **Test**, then **Connect**.

### MEGA

Saves documents to MEGA cloud storage.

1. Enter your **MEGA email**, **MEGA password**, and **Folder path**.
2. Click **Test**, then **Connect**.

### Nextcloud

Saves documents to a Nextcloud server, including one you run yourself.

1. If you use two-step sign-in, create an app password in your Nextcloud security settings.
2. Enter the **Nextcloud URL**, **Username**, **Password / App password**, and **Folder path**.
3. Click **Test**, then **Connect**.

---

## Calendar

### Google Calendar

**Paid.** When you set an interview date on a job, Peregrine adds an event to your Google Calendar.

1. Prepare a Google service account and share your calendar with it.
2. Enter the **Calendar ID** and the **Service Account JSON path**.
3. Click **Test**, then **Connect**.

### Apple Calendar (CalDAV)

**Paid.** Adds interview events to your Apple Calendar, or to any calendar that supports CalDAV. CalDAV is the standard way calendar apps talk to calendar servers.

1. Create an app-specific password in your Apple ID settings. Your normal Apple password will not work.
2. Enter the **CalDAV URL**, your **Apple ID / username**, the **App-Specific Password**, and the **Calendar name** (the default is "Interviews").
3. Click **Test**, then **Connect**.

---

## Notifications

### Slack

**Paid.** Posts a message to a Slack channel when something happens in your pipeline.

1. In Slack, create an incoming webhook for the channel you want. A webhook is a private web address that accepts messages.
2. Enter the **Incoming Webhook URL**. The **Channel (optional)** field is there if you want to name one.
3. Click **Test**, then **Connect**.

### Discord

**Free.** Posts messages to a Discord channel through a webhook.

1. In Discord, open your channel settings and create a webhook.
2. Enter the **Webhook URL**.
3. Click **Test**, then **Connect**.

### Home Assistant

**Free.** Sends pipeline events to Home Assistant, the home automation app. Useful for dashboards or your own automations.

1. In Home Assistant, create a long-lived access token from your profile page.
2. Enter the **Home Assistant URL**, the **Long-Lived Access Token**, and the **Notification service**.
3. Click **Test**, then **Connect**.

---

## If something looks wrong

- **The card says Disconnected after I clicked Connect.** The test did not pass. Read the short reason next to **✗**, check the fields, and try again.
- **A password is rejected.** Many services need an app password instead of your normal login. Create one in that service's security settings.
- **The list is empty.** If you see "No integrations registered", reload the page. If it stays empty, tell the CircuitForge team.

Your details are stored on your own install or your own account. Nothing is shared with a service until you click **Connect**.

??? note "For self-hosters and developers"
    **Where credentials live.** Each connected service is saved as `config/integrations/<name>.yaml`. These files are gitignored and must never be committed. Fields marked as passwords or tokens are stored in that file in plain text, so protect the file with normal file permissions. The service names are `notion`, `airtable`, `google_sheets`, `google_drive`, `dropbox`, `onedrive`, `mega`, `nextcloud`, `google_calendar`, `apple_calendar`, `slack`, `discord`, and `home_assistant`. See [Config Files](../reference/config-files.md).

    **Google services.** Google Sheets, Google Drive, and Google Calendar read a service account key from the path you give in **Service Account JSON path**. The path must be readable by the Peregrine process.

    **Tier gates.** Defined in `scripts/wizard/tiers.py`. Paid: `notion_sync`, `google_sheets_sync`, `airtable_sync`, `google_calendar_sync`, `apple_calendar_sync`, `slack_notifications`. Free: Google Drive, Dropbox, OneDrive, MEGA, Nextcloud, Discord, Home Assistant. Integrations are not in `BYOK_UNLOCKABLE`. See [Tier System](../reference/tier-system.md).

    **API.** The Connections page uses these routes in `dev_api.py`:

    - `GET /api/settings/system/integrations`
    - `POST /api/settings/system/integrations/{integration_id}/test`
    - `POST /api/settings/system/integrations/{integration_id}/connect`
    - `POST /api/settings/system/integrations/{integration_id}/disconnect`

    **Connection status.** Connected means the credentials file exists and the last test passed. Disconnected means there is no credentials file.

    **Adding your own integration.** See [Adding an Integration](../developer-guide/adding-integrations.md).
