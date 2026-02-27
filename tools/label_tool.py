"""Email Label Tool — card-stack UI for building classifier benchmark data.

Philosophy: Scrape → Store → Process
  Fetch (IMAP, wide search, multi-account) → data/email_label_queue.jsonl
  Label (card stack)                       → data/email_score.jsonl

Run:
    conda run -n job-seeker streamlit run tools/label_tool.py --server.port 8503

Config: config/label_tool.yaml  (gitignored — see config/label_tool.yaml.example)
"""
from __future__ import annotations

import email as _email_lib
import hashlib
import html as _html
import imaplib
import json
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header as _raw_decode
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

# ── Path setup ─────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

_QUEUE_FILE = _ROOT / "data" / "email_label_queue.jsonl"
_SCORE_FILE = _ROOT / "data" / "email_score.jsonl"
_CFG_FILE   = _ROOT / "config" / "label_tool.yaml"

# ── Labels ─────────────────────────────────────────────────────────────────
LABELS = [
    "interview_scheduled",
    "offer_received",
    "rejected",
    "positive_response",
    "survey_received",
    "neutral",
    "event_rescheduled",
    "unrelated",
    "digest",
]

_LABEL_META: dict[str, dict] = {
    "interview_scheduled": {"emoji": "🗓️", "color": "#4CAF50", "key": "1"},
    "offer_received":      {"emoji": "🎉", "color": "#2196F3", "key": "2"},
    "rejected":            {"emoji": "❌", "color": "#F44336", "key": "3"},
    "positive_response":   {"emoji": "👍", "color": "#FF9800", "key": "4"},
    "survey_received":     {"emoji": "📋", "color": "#9C27B0", "key": "5"},
    "neutral":             {"emoji": "⬜", "color": "#607D8B", "key": "6"},
    "event_rescheduled":   {"emoji": "🔄", "color": "#FF5722", "key": "7"},
    "unrelated":           {"emoji": "🗑️", "color": "#757575", "key": "8"},
    "digest":              {"emoji": "📰", "color": "#00BCD4", "key": "9"},
}

# ── HTML sanitiser ───────────────────────────────────────────────────────────
# Valid chars per XML 1.0 §2.2 (same set HTML5 innerHTML enforces):
#   #x9 | #xA | #xD | [#x20–#xD7FF] | [#xE000–#xFFFD] | [#x10000–#x10FFFF]
# Anything outside this range causes InvalidCharacterError in the browser.
_INVALID_XML_CHARS = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)

def _to_html(text: str, newlines_to_br: bool = False) -> str:
    """Strip invalid XML chars, HTML-escape the result, optionally convert \\n → <br>."""
    if not text:
        return ""
    cleaned = _INVALID_XML_CHARS.sub("", text)
    escaped = _html.escape(cleaned)
    if newlines_to_br:
        escaped = escaped.replace("\n", "<br>")
    return escaped


# ── Wide IMAP search terms (cast a net across all 9 categories) ─────────────
_WIDE_TERMS = [
    # interview_scheduled
    "interview", "phone screen", "video call", "zoom link", "schedule a call",
    # offer_received
    "offer letter", "job offer", "offer of employment", "pleased to offer",
    # rejected
    "unfortunately", "not moving forward", "other candidates", "regret to inform",
    "no longer", "decided not to", "decided to go with",
    # positive_response
    "opportunity", "interested in your background", "reached out", "great fit",
    "exciting role", "love to connect",
    # survey_received
    "assessment", "questionnaire", "culture fit", "culture-fit", "online assessment",
    # neutral / ATS confirms
    "application received", "thank you for applying", "application confirmation",
    "you applied", "your application for",
    # event_rescheduled
    "reschedule", "rescheduled", "new time", "moved to", "postponed", "new date",
    # digest
    "job digest", "jobs you may like", "recommended jobs", "jobs for you",
    "new jobs", "job alert",
    # general recruitment
    "application", "recruiter", "recruiting", "hiring", "candidate",
]


# ── IMAP helpers ────────────────────────────────────────────────────────────

def _decode_str(value: str | None) -> str:
    if not value:
        return ""
    parts = _raw_decode(value)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return " ".join(out).strip()


def _extract_body(msg: Any) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    return part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            return msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return ""


def _fetch_account(cfg: dict, days: int, limit: int, known_keys: set[str],
                   progress_cb=None) -> list[dict]:
    """Fetch emails from one IMAP account using wide recruitment search terms."""
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    host     = cfg.get("host", "imap.gmail.com")
    port     = int(cfg.get("port", 993))
    use_ssl  = cfg.get("use_ssl", True)
    username = cfg["username"]
    password = cfg["password"]
    name     = cfg.get("name", username)

    conn = (imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4)(host, port)
    conn.login(username, password)

    seen_uids: dict[bytes, None] = {}
    conn.select("INBOX", readonly=True)
    for term in _WIDE_TERMS:
        try:
            _, data = conn.search(None, f'(SUBJECT "{term}" SINCE "{since}")')
            for uid in (data[0] or b"").split():
                seen_uids[uid] = None
        except Exception:
            pass

    emails: list[dict] = []
    uids = list(seen_uids.keys())[:limit * 3]  # overfetch; filter after dedup
    for i, uid in enumerate(uids):
        if len(emails) >= limit:
            break
        if progress_cb:
            progress_cb(i / len(uids), f"{name}: {len(emails)} fetched…")
        try:
            _, raw_data = conn.fetch(uid, "(RFC822)")
            if not raw_data or not raw_data[0]:
                continue
            msg  = _email_lib.message_from_bytes(raw_data[0][1])
            subj = _decode_str(msg.get("Subject", ""))
            from_addr = _decode_str(msg.get("From", ""))
            date  = _decode_str(msg.get("Date", ""))
            body  = _extract_body(msg)[:800]
            entry = {
                "subject":   subj,
                "body":      body,
                "from_addr": from_addr,
                "date":      date,
                "account":   name,
            }
            key = _entry_key(entry)
            if key not in known_keys:
                known_keys.add(key)
                emails.append(entry)
        except Exception:
            pass

    try:
        conn.logout()
    except Exception:
        pass
    return emails


# ── Queue / score file helpers ───────────────────────────────────────────────

def _entry_key(e: dict) -> str:
    return hashlib.md5(
        (e.get("subject", "") + (e.get("body") or "")[:100]).encode()
    ).hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def _save_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── Config ──────────────────────────────────────────────────────────────────

def _load_config() -> list[dict]:
    if not _CFG_FILE.exists():
        return []
    cfg = yaml.safe_load(_CFG_FILE.read_text()) or {}
    return cfg.get("accounts", [])


# ── Page setup ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Email Labeler",
    page_icon="📬",
    layout="wide",
)

st.markdown("""
<style>
/* Card stack */
.email-card {
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 14px;
    padding: 28px 32px;
    box-shadow: 0 6px 24px rgba(0,0,0,0.18);
    margin-bottom: 4px;
    position: relative;
}
.card-stack-hint {
    height: 10px;
    border-radius: 0 0 12px 12px;
    border: 1px solid rgba(128,128,128,0.15);
    margin: 0 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.10);
}
.card-stack-hint2 {
    height: 8px;
    border-radius: 0 0 10px 10px;
    border: 1px solid rgba(128,128,128,0.08);
    margin: 0 32px;
}
/* Subject line */
.card-subject { font-size: 1.3rem; font-weight: 700; margin-bottom: 6px; }
.card-meta { font-size: 0.82rem; opacity: 0.6; margin-bottom: 16px; }
.card-body { font-size: 0.92rem; opacity: 0.85; white-space: pre-wrap; line-height: 1.5; }
/* Bucket buttons */
div[data-testid="stButton"] > button.bucket-btn {
    height: 70px;
    font-size: 1.05rem;
    font-weight: 600;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

st.title("📬 Email Label Tool")
st.caption("Scrape → Store → Process  |  card-stack edition")

# ── Session state init ───────────────────────────────────────────────────────

if "queue" not in st.session_state:
    st.session_state.queue: list[dict] = _load_jsonl(_QUEUE_FILE)

if "labeled" not in st.session_state:
    st.session_state.labeled: list[dict] = _load_jsonl(_SCORE_FILE)
    st.session_state.labeled_keys: set[str] = {
        _entry_key(r) for r in st.session_state.labeled
    }

if "idx" not in st.session_state:
    # Start past already-labeled entries in the queue
    labeled_keys = st.session_state.labeled_keys
    for i, entry in enumerate(st.session_state.queue):
        if _entry_key(entry) not in labeled_keys:
            st.session_state.idx = i
            break
    else:
        st.session_state.idx = len(st.session_state.queue)

if "history" not in st.session_state:
    st.session_state.history: list[tuple[int, str]] = []  # (queue_idx, label)


# ── Sidebar stats ────────────────────────────────────────────────────────────

with st.sidebar:
    labeled = st.session_state.labeled
    queue   = st.session_state.queue
    unlabeled = [e for e in queue if _entry_key(e) not in st.session_state.labeled_keys]

    st.metric("✅ Labeled", len(labeled))
    st.metric("📥 Queue", len(unlabeled))

    if labeled:
        st.caption("**Label distribution**")
        counts = {lbl: 0 for lbl in LABELS}
        for r in labeled:
            counts[r.get("label", "")] = counts.get(r.get("label", ""), 0) + 1
        for lbl in LABELS:
            m = _LABEL_META[lbl]
            st.caption(f"{m['emoji']} {lbl}: **{counts[lbl]}**")


# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_label, tab_fetch, tab_stats = st.tabs(["🃏 Label", "📥 Fetch", "📊 Stats"])


# ══════════════════════════════════════════════════════════════════════════════
# FETCH TAB
# ══════════════════════════════════════════════════════════════════════════════

with tab_fetch:
    accounts = _load_config()

    if not accounts:
        st.warning(
            f"No accounts configured. Copy `config/label_tool.yaml.example` → "
            f"`config/label_tool.yaml` and add your IMAP accounts.",
            icon="⚠️",
        )
    else:
        st.markdown(f"**{len(accounts)} account(s) configured:**")
        for acc in accounts:
            st.caption(f"• {acc.get('name', acc.get('username'))} ({acc.get('host')})")

    col_days, col_limit = st.columns(2)
    days  = col_days.number_input("Days back", min_value=7, max_value=730, value=180)
    limit = col_limit.number_input("Max emails per account", min_value=10, max_value=1000, value=150)

    all_accs = [a.get("name", a.get("username")) for a in accounts]
    selected = st.multiselect("Accounts to fetch", all_accs, default=all_accs)

    if st.button("📥 Fetch from IMAP", disabled=not accounts or not selected, type="primary"):
        existing_keys = {_entry_key(e) for e in st.session_state.queue}
        existing_keys.update(st.session_state.labeled_keys)

        fetched_all: list[dict] = []
        status = st.status("Fetching…", expanded=True)
        _live = status.empty()

        for acc in accounts:
            name = acc.get("name", acc.get("username"))
            if name not in selected:
                continue
            status.write(f"Connecting to **{name}**…")
            try:
                emails = _fetch_account(
                    acc, days=int(days), limit=int(limit),
                    known_keys=existing_keys,
                    progress_cb=lambda p, msg: _live.markdown(f"⏳ {msg}"),
                )
                _live.empty()
                fetched_all.extend(emails)
                status.write(f"✓ {name}: {len(emails)} new emails")
            except Exception as e:
                _live.empty()
                status.write(f"✗ {name}: {e}")

        if fetched_all:
            _save_jsonl(_QUEUE_FILE, st.session_state.queue + fetched_all)
            st.session_state.queue = _load_jsonl(_QUEUE_FILE)
            # Reset idx to first unlabeled
            labeled_keys = st.session_state.labeled_keys
            for i, entry in enumerate(st.session_state.queue):
                if _entry_key(entry) not in labeled_keys:
                    st.session_state.idx = i
                    break
            status.update(label=f"Done — {len(fetched_all)} new emails added to queue", state="complete")
        else:
            status.update(label="No new emails found (all already in queue or score file)", state="complete")


# ══════════════════════════════════════════════════════════════════════════════
# LABEL TAB
# ══════════════════════════════════════════════════════════════════════════════

with tab_label:
    queue   = st.session_state.queue
    labeled_keys = st.session_state.labeled_keys
    idx     = st.session_state.idx

    # Advance idx past already-labeled entries
    while idx < len(queue) and _entry_key(queue[idx]) in labeled_keys:
        idx += 1
    st.session_state.idx = idx

    unlabeled = [e for e in queue if _entry_key(e) not in labeled_keys]
    total_in_queue = len(queue)
    n_labeled = len(st.session_state.labeled)

    if not queue:
        st.info("Queue is empty — go to **Fetch** to pull emails from IMAP.", icon="📥")
    elif not unlabeled:
        st.success(
            f"🎉 All {n_labeled} emails labeled! Go to **Stats** to review and export.",
            icon="✅",
        )
    else:
        # Progress
        labeled_in_queue = total_in_queue - len(unlabeled)
        progress_pct = labeled_in_queue / total_in_queue if total_in_queue else 0
        st.progress(progress_pct, text=f"{labeled_in_queue} / {total_in_queue} labeled in queue")

        # Current email
        entry = queue[idx]

        # Card HTML
        subj  = entry.get("subject", "(no subject)") or "(no subject)"
        from_ = entry.get("from_addr", "") or ""
        date_ = entry.get("date", "") or ""
        acct  = entry.get("account", "") or ""
        body  = (entry.get("body") or "").strip()

        st.markdown(
            f"""<div class="email-card">
<div class="card-meta">{_to_html(from_)} &nbsp;·&nbsp; {_to_html(date_[:16])} &nbsp;·&nbsp; <em>{_to_html(acct)}</em></div>
<div class="card-subject">{_to_html(subj)}</div>
<div class="card-body">{_to_html(body[:500], newlines_to_br=True)}</div>
</div>""",
            unsafe_allow_html=True,
        )
        if len(body) > 500:
            with st.expander("Show full body"):
                st.text(body)

        # Stack hint (visual depth)
        st.markdown('<div class="card-stack-hint"></div>', unsafe_allow_html=True)
        st.markdown('<div class="card-stack-hint2"></div>', unsafe_allow_html=True)

        st.markdown("")  # spacer

        # ── Bucket buttons ────────────────────────────────────────────────
        def _do_label(label: str) -> None:
            row = {"subject": entry.get("subject", ""), "body": body[:600], "label": label}
            st.session_state.labeled.append(row)
            st.session_state.labeled_keys.add(_entry_key(entry))
            _append_jsonl(_SCORE_FILE, row)
            st.session_state.history.append((idx, label))
            # Advance
            next_idx = idx + 1
            while next_idx < len(queue) and _entry_key(queue[next_idx]) in labeled_keys:
                next_idx += 1
            st.session_state.idx = next_idx

        # Pre-compute per-label counts once
        _counts: dict[str, int] = {}
        for _r in st.session_state.labeled:
            _lbl_r = _r.get("label", "")
            _counts[_lbl_r] = _counts.get(_lbl_r, 0) + 1

        row1_cols = st.columns(3)
        row2_cols = st.columns(3)
        row3_cols = st.columns(3)
        bucket_pairs = [
            (row1_cols[0], "interview_scheduled"),
            (row1_cols[1], "offer_received"),
            (row1_cols[2], "rejected"),
            (row2_cols[0], "positive_response"),
            (row2_cols[1], "survey_received"),
            (row2_cols[2], "neutral"),
            (row3_cols[0], "event_rescheduled"),
            (row3_cols[1], "unrelated"),
            (row3_cols[2], "digest"),
        ]
        for col, lbl in bucket_pairs:
            m = _LABEL_META[lbl]
            cnt = _counts.get(lbl, 0)
            label_display = f"{m['emoji']} **{lbl}** [{cnt}]\n`{m['key']}`"
            if col.button(label_display, key=f"lbl_{lbl}", use_container_width=True):
                _do_label(lbl)
                st.rerun()

        # ── Wildcard label ─────────────────────────────────────────────────
        if "show_custom" not in st.session_state:
            st.session_state.show_custom = False

        other_col, _ = st.columns([1, 2])
        if other_col.button("🏷️ Other… `0`", key="lbl_other_toggle", use_container_width=True):
            st.session_state.show_custom = not st.session_state.show_custom
            st.rerun()

        if st.session_state.get("show_custom"):
            custom_cols = st.columns([3, 1])
            custom_val = custom_cols[0].text_input(
                "Custom label:", key="custom_label_text",
                placeholder="e.g. linkedin_outreach",
                label_visibility="collapsed",
            )
            if custom_cols[1].button(
                "✓ Apply", key="apply_custom", type="primary",
                disabled=not (custom_val or "").strip(),
            ):
                _do_label(custom_val.strip().lower().replace(" ", "_"))
                st.session_state.show_custom = False
                st.rerun()

        # ── Navigation ────────────────────────────────────────────────────
        st.markdown("")
        nav_cols = st.columns([2, 1, 1])

        remaining = len(unlabeled) - 1
        nav_cols[0].caption(f"**{remaining}** remaining  ·  Keys: 1–9 = label, 0 = other, S = skip, U = undo")

        if nav_cols[1].button("↩ Undo", disabled=not st.session_state.history, use_container_width=True):
            prev_idx, prev_label = st.session_state.history.pop()
            # Remove the last labeled entry
            if st.session_state.labeled:
                removed = st.session_state.labeled.pop()
                st.session_state.labeled_keys.discard(_entry_key(removed))
                _save_jsonl(_SCORE_FILE, st.session_state.labeled)
            st.session_state.idx = prev_idx
            st.rerun()

        if nav_cols[2].button("→ Skip", use_container_width=True):
            next_idx = idx + 1
            while next_idx < len(queue) and _entry_key(queue[next_idx]) in labeled_keys:
                next_idx += 1
            st.session_state.idx = next_idx
            st.rerun()

        # Keyboard shortcut capture (JS → hidden button click)
        st.components.v1.html(
            """<script>
document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const keyToLabel = {
        '1':'interview_scheduled','2':'offer_received','3':'rejected',
        '4':'positive_response','5':'survey_received','6':'neutral',
        '7':'event_rescheduled','8':'unrelated','9':'digest'
    };
    const label = keyToLabel[e.key];
    if (label) {
        const btns = window.parent.document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.toLowerCase().includes(label.replace('_',' '))) {
                btn.click(); break;
            }
        }
    } else if (e.key === '0') {
        const btns = window.parent.document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.includes('Other')) { btn.click(); break; }
        }
    } else if (e.key.toLowerCase() === 's') {
        const btns = window.parent.document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.includes('Skip')) { btn.click(); break; }
        }
    } else if (e.key.toLowerCase() === 'u') {
        const btns = window.parent.document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.includes('Undo')) { btn.click(); break; }
        }
    }
});
</script>""",
            height=0,
        )


# ══════════════════════════════════════════════════════════════════════════════
# STATS TAB
# ══════════════════════════════════════════════════════════════════════════════

with tab_stats:
    labeled = st.session_state.labeled

    if not labeled:
        st.info("No labeled emails yet.")
    else:
        counts: dict[str, int] = {}
        for r in labeled:
            lbl = r.get("label", "")
            if lbl:
                counts[lbl] = counts.get(lbl, 0) + 1

        st.markdown(f"**{len(labeled)} labeled emails total**")

        # Show known labels first, then any custom labels
        all_display_labels = list(LABELS) + [l for l in counts if l not in LABELS]
        max_count = max(counts.values()) if counts else 1
        for lbl in all_display_labels:
            if lbl not in counts:
                continue
            m = _LABEL_META.get(lbl)
            emoji = m["emoji"] if m else "🏷️"
            col_name, col_bar, col_n = st.columns([3, 5, 1])
            col_name.markdown(f"{emoji} {lbl}")
            col_bar.progress(counts[lbl] / max_count)
            col_n.markdown(f"**{counts[lbl]}**")

        st.divider()

        # Export hint
        st.caption(
            f"Score file: `{_SCORE_FILE.relative_to(_ROOT)}`  "
            f"({_SCORE_FILE.stat().st_size if _SCORE_FILE.exists() else 0:,} bytes)"
        )
        if st.button("🔄 Re-sync from disk"):
            st.session_state.labeled = _load_jsonl(_SCORE_FILE)
            st.session_state.labeled_keys = {_entry_key(r) for r in st.session_state.labeled}
            st.rerun()

        if _SCORE_FILE.exists():
            st.download_button(
                "⬇️ Download email_score.jsonl",
                data=_SCORE_FILE.read_bytes(),
                file_name="email_score.jsonl",
                mime="application/jsonlines",
            )
