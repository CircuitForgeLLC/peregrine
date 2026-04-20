-- messages: manual log entries and LLM drafts
CREATE TABLE IF NOT EXISTS messages (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id          INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
  job_contact_id  INTEGER REFERENCES job_contacts(id) ON DELETE SET NULL,
  type            TEXT NOT NULL DEFAULT 'email',
  direction       TEXT,
  subject         TEXT,
  body            TEXT,
  from_addr       TEXT,
  to_addr         TEXT,
  logged_at       TEXT NOT NULL DEFAULT (datetime('now')),
  approved_at     TEXT,
  template_id     INTEGER REFERENCES message_templates(id) ON DELETE SET NULL,
  osprey_call_id  TEXT
);

-- message_templates: built-in seeds and user-created templates
CREATE TABLE IF NOT EXISTS message_templates (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  key              TEXT UNIQUE,
  title            TEXT NOT NULL,
  category         TEXT NOT NULL DEFAULT 'custom',
  subject_template TEXT,
  body_template    TEXT NOT NULL,
  is_builtin       INTEGER NOT NULL DEFAULT 0,
  is_community     INTEGER NOT NULL DEFAULT 0,
  community_source TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO message_templates
  (key, title, category, subject_template, body_template, is_builtin)
VALUES
  (
    'follow_up',
    'Following up on my application',
    'follow_up',
    'Following up — {{role}} application',
    'Hi {{recruiter_name}},

I wanted to follow up on my application for the {{role}} position at {{company}}. I remain very interested in the opportunity and would welcome the chance to discuss my background further.

Please let me know if there is anything else you need from me.

Best regards,
{{name}}',
    1
  ),
  (
    'thank_you',
    'Thank you for the interview',
    'thank_you',
    'Thank you — {{role}} interview',
    'Hi {{recruiter_name}},

Thank you for taking the time to speak with me about the {{role}} role at {{company}}. I enjoyed learning more about the team and the work you are doing.

I am very excited about this opportunity and look forward to hearing about the next steps.

Best regards,
{{name}}',
    1
  ),
  (
    'accommodation_request',
    'Accommodation request',
    'accommodation',
    'Accommodation request — {{role}} interview',
    'Hi {{recruiter_name}},

I am writing to request a reasonable accommodation for my upcoming interview for the {{role}} position. Specifically, I would appreciate:

{{accommodation_details}}

Please let me know if you need any additional information. I am happy to discuss this further.

Thank you,
{{name}}',
    1
  ),
  (
    'withdrawal',
    'Withdrawing my application',
    'withdrawal',
    'Application withdrawal — {{role}}',
    'Hi {{recruiter_name}},

I am writing to let you know that I would like to withdraw my application for the {{role}} position at {{company}}.

Thank you for your time and consideration. I wish you and the team all the best.

Best regards,
{{name}}',
    1
  )
