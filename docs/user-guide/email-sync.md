# Email Sync

Peregrine monitors your inbox for job-related emails and automatically updates job stages when it detects interview requests, rejections, offers, and survey links.

---

## Configuration

Email sync is configured in `config/email.yaml` (gitignored). Copy the example template to get started:

```bash
cp config/email.yaml.example config/email.yaml
```

Then fill in your credentials:

```yaml
host: imap.gmail.com
port: 993
use_ssl: true
username: your.email@gmail.com
password: xxxx-xxxx-xxxx-xxxx   # see Gmail App Password below
sent_folder: ""                  # leave blank to auto-detect
lookback_days: 90                # how many days back to scan
todo_label: ""                   # optional Gmail label to monitor
```

You can also configure email sync via **Settings → Email** in the UI.

---

## Gmail Setup

Gmail requires an **App Password** instead of your regular account password. Your regular password will not work.

1. Enable **2-Step Verification** on your Google Account at [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create a new app password — name it "Peregrine" or similar
4. Copy the 16-character code (no spaces) and paste it as `password` in `config/email.yaml`
5. Enable IMAP in Gmail: **Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP**

---

## Outlook / Office 365

```yaml
host: outlook.office365.com
port: 993
use_ssl: true
username: your.email@company.com
password: your-password           # or App Password if MFA is enabled
```

---

## Gmail Label Monitoring (Optional)

If you use a Gmail label to flag action-needed job emails (e.g. "TO DO JOBS"), set:

```yaml
todo_label: "TO DO JOBS"
```

Emails in this label are matched to pipeline jobs by company name, then filtered by action keywords in the subject line (e.g. "interview", "next steps", "offer").

---

## Email Classification Labels

The email classifier assigns one of six labels to each relevant email:

| Label | Meaning |
|-------|---------|
| `interview_request` | Recruiter or hiring manager requesting a call or interview |
| `rejection` | Automated or personal rejection |
| `offer` | Job offer letter or verbal offer notification |
| `follow_up` | Candidate or recruiter follow-up with no stage change |
| `survey_received` | Link or request to complete a culture-fit or skills assessment |
| `other` | Job-related but does not fit any category above |

Classification is performed by your configured LLM backend. The classifier uses the email subject and body as input.

!!! note "Tier requirement"
    Email classification is a Paid feature.

---

## Stage Auto-Updates

When a classified email is matched to a job in your pipeline, Peregrine updates the job stage automatically:

| Classification | Stage action |
|---------------|-------------|
| `interview_request` | Moves `applied` → `phone_screen` |
| `rejection` | Moves job → `rejected` (captures `rejection_stage`) |
| `offer` | Flags job for review; moves toward `offer` stage |
| `survey_received` | Moves job → `survey` pre-stage |

Emails are matched to jobs by comparing the sender domain and company name in the email body against company names in your pipeline.

---

## Running Email Sync

### From the UI

Click **Sync Emails** on the Home page. This runs as a background task — you can navigate away while it processes.

### Non-blocking background sync

Email sync runs in a daemon thread via `scripts/task_runner.py` and does not block the UI. The sidebar background task indicator shows sync progress.

---

## Email Thread Log

All matched emails are stored in the `job_contacts` table (one row per email thread per job). You can view the thread log for any job from the Job Review detail view or the Interviews kanban card.

Columns stored: `direction` (inbound/outbound), `subject`, `from`, `to`, `body`, `received_at`.
