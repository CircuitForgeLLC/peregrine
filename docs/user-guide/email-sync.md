# Email Sync

Email sync lets Peregrine read your inbox for replies about jobs you applied to, so you do not have to copy them in by hand.

It is optional. Everything else in Peregrine works without it.

## What you will do here

1. Make an app password with your email provider. This is a separate password just for Peregrine.
2. Open **Settings**, then **Connections**.
3. Pick your provider and fill in the form.
4. Click **Test Connection**. You should see **✓ Connected**.
5. Click **Save Email Config**.
6. Click **Sync Emails** on **Home** or on **Interviews**.

## What does Peregrine do with my email?

When you click **Sync Emails**, Peregrine:

- Looks back through your inbox and sent folder. The default is 90 days.
- Looks for messages that mention companies you applied to and have job-related words in the subject, like "interview", "application", or "next steps".
- Saves a copy of each match to that job. You can read them in **Email History** on the **Interview Prep** page and on the **Messages** page.
- Uses a writing assistant (a large language model, or LLM) to guess what each email is about. For example an interview request, an offer, a survey, or a rejection.
- Shows that guess as a small banner on the job in **Interviews**. You decide what to do with it. See [Interviews](interviews.md).
- May add a new job to your list when a recruiter writes to you about a role you never searched for. It appears as a lead for you to review, and it is up to you whether to keep it.

## What does it never do?

- It never sends email for you. Draft replies are written for you to review, edit, and send yourself.
- It never deletes, moves, or files your messages.
- It never moves a job to a new stage on its own. A banner is only a suggestion.
- It never needs your regular email password. You give it an app password instead.

One side effect to know about: some email providers mark a message as read once an app opens it. If that matters to you, check your inbox after the first sync.

## Where do my password and emails go?

Be clear about two kinds of setup.

**Self-hosted (you run Peregrine yourself).** Your app password is stored on your own machine. It uses your operating system's secure keychain when one is available. If not, it goes in an encrypted file next to the app. It is never shown back to you in the form once saved. Your saved emails live in Peregrine's database on your machine.

**Hosted by CircuitForge.** Your password and saved emails are kept in your own account's private storage on our server, separate from other users.

The one thing to think about is the writing assistant that classifies each email. It receives the subject and the start of the message body. If your Peregrine uses a model running on your own machine, that text stays there. If you have set up a cloud model with your own key, that text goes to that provider. Your model choices are set in **Settings**.

## How do I connect Gmail?

Gmail needs an app password. Your normal Google password will not work.

1. Turn on **2-Step Verification** in your Google Account.
2. In **Settings** then **Connections** in Peregrine, choose **Gmail** under **Provider**. Click **Get an app password →** to jump straight to Google's page.
3. Create an app password and name it "Peregrine".
4. Copy the 16-character code and paste it into **Password / App Password**.
5. Type your Gmail address under **Username**.
6. Click **Test Connection**, then **Save Email Config**.

Choosing a provider fills in the server details for you, so you do not need to type them.

## How do I connect Outlook, iCloud, or Yahoo?

The steps are the same. Choose **Outlook / Microsoft 365**, **iCloud Mail**, or **Yahoo Mail** under **Provider**. Click **Get an app password →**, make one, and paste it in. Then **Test Connection** and **Save Email Config**.

Using a different email provider? Leave **Provider** on **Custom / other** and fill in the details your provider gives you. Look for "IMAP settings" in their help pages. IMAP is the method email apps use to read your mail.

## What do the other fields mean?

- **IMAP Host** and **Port** are the server address and its door number. A provider choice fills these in.
- **Use SSL** keeps the connection private. Leave it on.
- **Sent Folder** is where your sent mail lives. Leave the preset in place.
- **Lookback Days** is how far back to read. A smaller number is faster and reads less.

## If something looks wrong

- **✗ Failed** after **Test Connection**: the most common cause is using your normal password instead of an app password. Make a new app password and paste it in again.
- **Email not configured** on **Interviews**: email sync has not been saved yet. Finish the steps above.
- **⚠ Sync failed**: click it to try again. If it keeps failing, run **Test Connection** to check your details.
- A banner is wrong: open it with **▸ Read** and use **Re-classify** to fix it. You are not doing anything wrong, and the assistant makes mistakes.

!!! note "Paid feature"
    Email reading and classification are part of the Paid tier. Bringing your own LLM key does not unlock this one. See [Tier System](../reference/tier-system.md).

## How do I disconnect?

There is no single "Disconnect" button for email. Use whichever of these fits:

1. **Stop access for good.** Delete the "Peregrine" app password in your email provider's security page. Peregrine can no longer read your mail, immediately.
2. **Stop syncing.** Simply do not click **Sync Emails**. Nothing runs in the background without you asking.
3. **Delete what Peregrine saved.** On **Home**, open **⚠️ Danger Zone**, then **More options**, then **📧 Purge Email Data**. This removes every saved email thread and every job that came from an email. It cannot be undone. Jobs you added yourself are kept.

## What is the Digest page?

Job alert emails from sites like LinkedIn and Indeed often hold many jobs at once. If you mark one as **📰 Digest** (using **Re-classify** on a banner), it goes to the **Digest** page.

1. Open **Digest** in the sidebar. The number beside it shows how many are waiting.
2. Click **Extract** on an email. Peregrine finds the links in it.
3. Job-looking links are ticked for you. Untick any you do not want.
4. Click to queue them. They go to **Job Review** for you to approve or reject like any other job.
5. Click **✕** to remove an email from the queue.

## What is the Messages page?

**Messages** keeps one timeline per job. It holds saved emails, call notes, and drafts.

- **Log call** and **Log note** save what was said, with an optional date and time.
- **Use template** opens ready-made messages for follow-ups, thank-yous, accommodation requests, and withdrawals. Fill-in spots like the company and role are completed for you. You can also make your own templates.
- **Draft reply with LLM** writes a reply to the latest email they sent you. It appears as **Pending approval**. You can edit it, then click **Approve + copy** to copy it, or **Open in email client**, or **Discard** it. Nothing is ever sent for you.

The sidebar link for the page is **Messages**. It lists jobs you have applied to.

!!! note "Paid feature"
    Draft replies are part of the Paid tier. If you bring your own LLM key, they unlock without upgrading.

??? note "For self-hosters and developers"
    **Config file.** Non-secret settings live in `config/email.yaml` (gitignored, mode 600). The Settings form (`PUT /api/settings/system/email`) writes only these keys: `host`, `port`, `ssl`, `username`, `sent_folder`, `lookback_days`. Any other key, such as `todo_label`, is dropped when you save from the UI.

    ```yaml
    host: imap.gmail.com
    port: 993
    ssl: true
    username: your.email@gmail.com
    sent_folder: "[Gmail]/Sent Mail"   # blank = auto-detect
    lookback_days: 90
    ```

    **Password storage.** The Settings form stores the password through `scripts/credential_store.py` under service `peregrine`, key `imap_password`. Backend is set by `CREDENTIAL_BACKEND` (`auto` tries the OS keyring, then falls back to a Fernet-encrypted file in `config/credentials/` with its key at `config/.credential_key`). In cloud mode each tenant gets its own credentials directory. A stored value of the form `${ENV_VAR}` is resolved from the environment at read time. The `GET` route never returns the password, only `password_set`. `POST /api/settings/system/email/test` always uses the stored credential and rejects non-public hosts.

    **Provider presets** (in `ConnectionsSettingsView.vue`): Gmail `imap.gmail.com` (`[Gmail]/Sent Mail`), Outlook `outlook.office365.com` (`Sent Items`), iCloud `imap.mail.me.com` (`Sent Messages`), Yahoo `imap.mail.yahoo.com` (`Sent`). All use port 993 with SSL. Gmail also needs IMAP enabled in Gmail settings under Forwarding and POP/IMAP.

    **Known gap to verify.** `scripts/imap_sync.py` `connect()` reads `cfg["password"]` from `config/email.yaml`, but the Settings form no longer writes the password to that file. Check that the sync path reads the credential store before relying on the Settings flow. Until confirmed, a hand-edited `password:` line in `config/email.yaml` is the path the sync code actually reads.

    **Sync flow.** `POST /api/email/sync` queues an `email_sync` background task. Status is at `GET /api/email/sync/status`. `scripts/task_runner.py` calls `sync_all()` in `scripts/imap_sync.py`. For every job in `applied`, `phone_screen`, `interviewing`, `offer`, or `hired` it searches the inbox and sent folder (read-only IMAP fetches) by company-name terms, applies a subject keyword filter, and stores rows in `job_contacts` (`direction`, `subject`, `from_addr`, `to_addr`, `body`, `received_at`, `message_id`, `stage_signal`). Messages are de-duplicated by `message_id`. It then scans the optional `todo_label` Gmail label and unmatched recruiter outreach (new jobs with `source='email'` and a synthetic `email://` URL).

    **Classification.** `classify_stage_signal()` uses `LLMRouter` and returns `interview_scheduled`, `offer_received`, `rejected`, `positive_response`, `survey_received`, or `neutral`. The first 400 characters of the body plus the subject are sent. Rejection and ATS-confirmation phrases are pre-filtered before any LLM call. Users can also set `event_rescheduled`, `unrelated`, and `digest` through `POST /api/stage-signals/{id}/reclassify`. The signal sets a banner only. It does not change job status.

    **Digest and messages APIs.** `/api/digest-queue` (list, add, delete), `/api/digest-queue/{id}/extract-links`, `/api/digest-queue/{id}/queue-jobs`. `/api/contacts` and `/api/contacts/{id}` list and read saved emails. `POST /api/contacts/{id}/draft-reply` writes the LLM draft.

    **Purge.** `POST /api/jobs/purge` with `target: "email"` deletes all `job_contacts` rows and jobs with `source='email'`.

    **Tiers.** `email_classifier` is Paid and is not in `BYOK_UNLOCKABLE`. `llm_reply_draft` is Paid and is BYOK-unlockable. See `scripts/wizard/tiers.py`.
