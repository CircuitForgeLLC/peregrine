# Settings

Settings is where you tell Peregrine who you are, what jobs to look for, and how it should connect to your email and other tools.

On a computer, the settings pages are listed down the left side. On a phone, they run across the top as a row of chips. The list below follows that same order.

## What you will do here

1. Open **Settings** from the sidebar. You will see the list of settings pages.
2. Pick the page that matches what you want to change. Each section below starts with the question you are likely asking.
3. Make your change and click the **Save** button on that page. A button that says "Saving…" means your change is on its way.

Some pages only appear on a self-hosted install (Peregrine running on your own computer or server). The pages that appear for everyone are marked below.

!!! note "Back to Setup"
    If you have not finished the setup checklist yet, a **← Back to Setup** link appears at the top of every settings page. It takes you back to the checklist. The checklist links into **My Profile**, **Resume Profile**, **Search Prefs**, **Connections**, and (self-hosted only) **System**.

For how settings fit into your day, see [Daily Workflow](daily-workflow.md).

---

## Profile

### How do I change my name, contact details, or career summary?

Open **My Profile**. The **Identity** section holds:

- **Full name**, **Email**, **Phone**, and **LinkedIn URL**. Peregrine uses these in cover letters and other documents.
- **Career summary**: two or three sentences about your experience and focus. Every cover letter draws on it.
- **Candidate voice**: a short note on how you write and communicate. Peregrine uses it to shape the tone of your cover letters.

Click **Save Identity** when you are done.

On Paid and Premium plans, a **Generate ✦** button sits under the career summary and the voice note. It offers a suggestion. You choose **Use this** to keep it or **Discard** to throw it away. Nothing changes until you pick one.

!!! note "Paid feature"
    The **Generate ✦** buttons are Paid. Some suggestion features also unlock when you connect your own LLM key (bring your own key, or BYOK). An LLM is a large language model, the technology behind the writing assistant.

Before setup is finished, you will also see a **Set up your profile with AI** banner. **Start AI setup** walks you through a few questions and fills in your profile for you. If your plan does not include it, the banner shows **Upgrade** instead.

### How do I tell Peregrine which industries I care about?

In **My Profile**, go to **Mission & Values**. Add an industry, such as music, and an optional personal note. When a job matches one of your industries, the cover letter draft includes your note.

- Click **+ Add mission** to add a row.
- Click **×** on a row to remove it.
- Click **Save Mission** when you are done.

### How do I keep a former employer private?

In **My Profile**, go to **NDA Companies**. Type a company name and click **Add**. Peregrine will describe that company as "previous employer (NDA)" in research briefs when the match score is low. Click **×** on a name to remove it.

### How do I add inclusion research to company briefs?

In **My Profile**, go to **Research Brief Preferences**. There are two checkboxes:

- **Include accessibility & inclusion research in company briefs**
- **Include LGBTQ+ inclusion research in company briefs**

These extra sections are for your own decision-making. They never appear in your applications. These checkboxes save as soon as you click them.

### How do I update my resume?

Open **Resume Profile**. This is the structured version of your resume that Peregrine uses when it drafts cover letters.

If you have not added a resume yet, you will see three choices:

- **Upload & Parse**: upload a PDF, DOCX (Word), or ODT (OpenDocument) file and Peregrine reads it for you.
- **Fill in Manually**: click **Start from Scratch** for a blank form.
- **Run Setup Wizard**: click **Open Setup Wizard →**. This choice appears on self-hosted installs only.

If you already have a resume, the full form opens. It has these sections:

- **Career Summary**
- **Personal Information**: name, email, phone, and LinkedIn URL are copied from **My Profile** and are shown here as read-only. Address, city, ZIP code, and date of birth are filled in here.
- **Work Experience**: job title, company, period, location, industry, and responsibilities. Click **+ Add Position** to add one or **Remove** to delete one.
- **Education**: click **+ Add education**.
- **Achievements**: awards, certifications, open-source projects, and publications.
- **Preferences & Availability**: minimum and maximum salary, and notice period.
- **Skills & Keywords**: tags for **Skills**, **Domains**, and **Keywords**. Type a tag and press Enter. Use **Suggest** to get ideas from your resume.

There is also an optional self-identification section (gender, pronouns, ethnicity, veteran status, disability). It is used only for your own tracking.

To replace your resume, use **Replace Resume**. It parses the new file and overwrites the data on this page.

Click **Save Resume** when you are done.

!!! note "Resume Profile and the Resume Library"
    The **Resume Library** is a separate page with saved copies of your full resume text. When a library entry is linked, a note on this page tells you when it was last synced. See [Daily Workflow](daily-workflow.md#your-resume-in-peregrine).

---

## Search

### How do I change the jobs Peregrine looks for?

Open **Search Prefs**. Your changes apply the next time you click **Run Discovery**.

- **Remote Preference**: pick **On-site**, **Remote**, **Hybrid**, or any mix. Jobs that do not match are left out before they reach your queue.
- **Job Titles**: type a title and press Enter. Click **×** on a title to remove it.
- **Locations**: the places to search. Leave it empty to search everywhere.
- **Exclude Keywords**: jobs with these words in the title are skipped.
- **Job Boards**: turn individual job boards on or off. A board marked **coming soon** is not working yet.
- **Custom Board URLs**: add a job board address of your own.
- **Blocklists**: companies, industries, or locations you never want to see.

Click **Suggest** next to **Job Titles**, **Locations**, or **Exclude Keywords** for ideas based on your resume. Suggestions appear as chips. Click one to add it. Ignore the ones you do not want.

Click **Save Search Preferences** when you are done.

---

## App

### How do I connect my email or other tools?

Open **Connections**. It has two parts:

- **Email (IMAP)**: lets Peregrine read your inbox so it can sort job emails into your Interviews pipeline. IMAP is the standard way email providers let apps read your mail.
- **Integrations**: optional links to Notion, Google Drive, Slack, and others.

To set up email, pick your **Provider** (Gmail, Outlook / Microsoft 365, iCloud Mail, or Yahoo Mail). Peregrine fills in the server details. Then:

1. Enter your **Username**, which is your email address.
2. Enter an app password in **Password / App Password**. A normal login password usually will not work. The **Get an app password →** link takes you to the right page at your provider.
3. Click **Save Email Config**, then **Test Connection**. You will see **✓ Connected** or **✗ Failed**.

Each service in the **Integrations** list shows **Connected** or **Disconnected**. Step-by-step instructions for each one are in [Integrations](integrations.md). For what email sync does, see [Email Sync](email-sync.md).

### How do I choose which model writes my drafts? (System, self-hosted only)

**System** is on self-hosted installs only. The hosted cloud version manages this for you, so you will not see the page there.

The page opens with a note: "This tab is only available in self-hosted mode." It contains:

- **LLM Backends**: the list of language model services Peregrine can use. Drag to reorder. The one at the top is tried first and the others are fallbacks. Each has an **Enabled** or **Disabled** switch.
- **Compute & AI Backend**: your **Hardware profile**, the **Find Ollama** and **Find vLLM** buttons that look for a model server already running on your machine, and optional **Anthropic API key** and **OpenAI-compatible endpoint** fields for cloud models.
- **Model Assignments**: choose which model handles **Primary (cover letters)**, **Research (suggestions)**, and **Chat (AI assistant)**. If a model may not follow instructions well for a task, you will see **⚠ May not follow instructions reliably**. It is a warning, not a block.
- **Services**: shows which helper services are running, with **Start** and **Stop** buttons.
- **File Paths**, **Deployment / Server**, and **Orchard Coordinator** for more advanced setups.

!!! note "Cloud keys send data to that provider"
    If you turn on a cloud backend, your job descriptions and cover letter text go to that provider. A confirmation box asks you to acknowledge this before it saves.

### How do I train a model on my own writing? (Fine-Tune)

**Fine-Tune** appears on self-hosted installs with a single-GPU or dual-GPU hardware profile, and on the hosted cloud version for Premium plans. Fine-tuning means teaching a model to write more like you, using your past cover letters.

1. Open **Fine-Tune** and find **Training Export**.
2. Turn on **Include cover letters in training export**. It is off until you choose it. When it is off, your cover letters stay local.
3. Under **From Applied Jobs**, review the pairs of job and cover letter. Click **Exclude** on any you do not want, or **Restore** to bring one back.
4. Click **Download JSONL** to save the file. It holds your cover letters in plain text, so keep it somewhere safe.

!!! note "Premium feature"
    **Request Cloud Fine-Tune** is Premium. Today it shows a "coming soon" message when clicked.

Self-hosted users also see a three-step flow: **1. Upload**, **2. Extract**, **3. Train**. You upload past cover letters (.md or .txt files), extract training pairs, review them, and then train. See the technical notes below for the training command.

---

## Account

### How do I see my plan or license? (License)

Open **License**.

- **Hosted cloud version**: the page shows your plan (**FREE**, **PAID**, or **PREMIUM**). Manage your subscription at circuitforge.tech/account.
- **Self-hosted**: if you have a key, you will see your plan, your license key, and a **Deactivate** button. If your key has lapsed, a **Grace period ends** date appears. If you have no key, enter it in **License Key** and click **Activate**.

**Deactivate** asks you to confirm. You lose paid features, and you can turn them back on later with the same key.

### How do I back up or restore my data? (Data, self-hosted only)

Open **Data**. The page is called **Data & Backup**.

- **Create Backup**: saves your settings as a zip file. Check **Include job database (staging.db)** to include your jobs too. After it finishes, you will see the number of files and the size.
- **Restore from Backup**: choose a backup zip and click **Restore**. A confirmation box warns that this overwrites your current settings.

### How do I delete my data?

- **Self-hosted**: your data lives on your own machine. To remove it, delete the Peregrine data folder. The technical notes below say where it is. The **Data** page does not have a delete button.
- **Hosted cloud version**: the **Data** page is not in the settings list, so there is no delete button in the app today. If you want your account data removed, ask the CircuitForge team through the contact details on circuitforge.tech.

### How do I control what gets shared? (Privacy)

Open **Privacy**. Nothing is collected unless you say so.

- **Self-hosted**: one checkbox, **Share anonymous usage statistics to help improve Peregrine**. It is off by default. If you turned on a cloud model, a notice explains that job descriptions and cover letter text go to that provider. Click **Got it, don't show again** to dismiss it.
- **Hosted cloud version**: **Disable all data collection (master off)** turns everything off at once. Below it, **Usage events (feature analytics)** and **Share content for model improvement** can be switched on or off one at a time.

Click **Save** when you are done.

---

## Developer

The **Developer** page appears only when developer mode is on or a tier override is set. It holds testing tools such as **Apply Override** for trying other plans, a **HuggingFace Token** field, **Reset Setup Wizard**, and an export of labeled emails. Most people never need it.

---

## If something looks wrong

- **A page is missing.** Some pages only show on certain installs or plans. **System** and **Data** are self-hosted only. **Fine-Tune** needs a GPU profile (self-hosted) or Premium (cloud). **Developer** is hidden unless developer mode is on.
- **My changes did not stick.** Look for a **Save** button at the bottom of that section and click it. Some pages have more than one.
- **Test Connection says Failed.** Check that you used an app password and not your normal password. Then try again.

??? note "For self-hosters and developers"
    **Where settings are stored.** Profile and preference data is written to `config/user.yaml`, search preferences to `config/search_profiles.yaml`, LLM backends to `config/llm.yaml`, and the structured resume to `config/plain_text_resume.yaml`. See [Config Files](../reference/config-files.md) for the full list and [Tier System](../reference/tier-system.md) for how plans gate features.

    **Developer page options.**

    | Option | Description |
    |--------|-------------|
    | Reset Setup Wizard | Sets `wizard_complete: false` so the wizard shows again on next load |
    | Override Tier | Sets the tier to `paid` or `premium` for UI testing only. It does not affect licensing |
    | HuggingFace Token | Stored securely. Used for model downloads and fine-tune uploads |
    | Export to `data/email_score.jsonl` | Exports labeled emails as JSONL for classifier training |

    **Page visibility rules** (from the settings navigation):

    - **System** and **Data**: shown when not in cloud mode.
    - **Fine-Tune**: self-hosted with `single-gpu` or `dual-gpu` inference profile, or cloud with Premium.
    - **Developer**: shown when dev mode is on or `dev_tier_override` is set.

    **Self-hosted fine-tuning.** After you upload and extract training pairs, the **Train Model** step shows `make finetune`, which runs Unsloth with Ollama. Use **Check Model Status** to see whether the `alex-cover-writer` model is registered in Ollama.

    **Deleting self-hosted data.** Stop the stack and remove the data directory configured under **System** > **File Paths** > **Data Directory** (default `data/`), plus the files in `config/`. Use **Create Backup** first if you want a copy.

    **Cloud: Custom Model.** The System page source contains a **Custom Model** section for cloud accounts (a **Model alias** field, Premium). The settings navigation hides **System** in cloud mode, so check the current build before relying on it.

    **Email password.** In the **Password / App Password** field you can type `${ENV_VAR_NAME}` to read the password from an environment variable instead of storing it.

    **Orchard Coordinator.** The **Coordinator URL** field (placeholder `https://orch.circuitforge.tech`) points Peregrine at a shared model coordinator.
