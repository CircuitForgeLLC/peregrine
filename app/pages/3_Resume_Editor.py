# app/pages/3_Resume_Editor.py
"""
Resume Editor — form-based editor for Alex's AIHawk profile YAML.
FILL_IN fields highlighted in amber.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

st.set_page_config(page_title="Resume Editor", page_icon="📝", layout="wide")
st.title("📝 Resume Editor")
st.caption("Edit Alex's application profile used by AIHawk for LinkedIn Easy Apply.")

RESUME_PATH = Path(__file__).parent.parent.parent / "aihawk" / "data_folder" / "plain_text_resume.yaml"

if not RESUME_PATH.exists():
    st.error(f"Resume file not found at `{RESUME_PATH}`. Is AIHawk cloned?")
    st.stop()

data = yaml.safe_load(RESUME_PATH.read_text()) or {}


def field(label: str, value: str, key: str, help: str = "", password: bool = False) -> str:
    """Render a text input, highlighted amber if value is FILL_IN or empty."""
    needs_attention = str(value).startswith("FILL_IN") or value == ""
    if needs_attention:
        st.markdown(
            '<p style="color:#F59E0B;font-size:0.8em;margin-bottom:2px">⚠️ Needs your attention</p>',
            unsafe_allow_html=True,
        )
    return st.text_input(label, value=value or "", key=key, help=help,
                         type="password" if password else "default")


st.divider()

# ── Personal Info ─────────────────────────────────────────────────────────────
with st.expander("👤 Personal Information", expanded=True):
    info = data.get("personal_information", {})
    col1, col2 = st.columns(2)
    with col1:
        name = field("First Name", info.get("name", ""), "pi_name")
        email = field("Email", info.get("email", ""), "pi_email")
        phone = field("Phone", info.get("phone", ""), "pi_phone")
        city = field("City", info.get("city", ""), "pi_city")
    with col2:
        surname = field("Last Name", info.get("surname", ""), "pi_surname")
        linkedin = field("LinkedIn URL", info.get("linkedin", ""), "pi_linkedin")
        zip_code = field("Zip Code", info.get("zip_code", ""), "pi_zip")
        dob = field("Date of Birth", info.get("date_of_birth", ""), "pi_dob",
                    help="Format: MM/DD/YYYY")

# ── Education ─────────────────────────────────────────────────────────────────
with st.expander("🎓 Education"):
    edu_list = data.get("education_details", [{}])
    updated_edu = []
    degree_options = ["Bachelor's Degree", "Master's Degree", "Some College",
                      "Associate's Degree", "High School", "Other"]
    for i, edu in enumerate(edu_list):
        st.markdown(f"**Entry {i+1}**")
        col1, col2 = st.columns(2)
        with col1:
            inst = field("Institution", edu.get("institution", ""), f"edu_inst_{i}")
            field_study = st.text_input("Field of Study", edu.get("field_of_study", ""), key=f"edu_field_{i}")
            start = st.text_input("Start Year", edu.get("start_date", ""), key=f"edu_start_{i}")
        with col2:
            current_level = edu.get("education_level", "Some College")
            level_idx = degree_options.index(current_level) if current_level in degree_options else 2
            level = st.selectbox("Degree Level", degree_options, index=level_idx, key=f"edu_level_{i}")
            end = st.text_input("Completion Year", edu.get("year_of_completion", ""), key=f"edu_end_{i}")
        updated_edu.append({
            "education_level": level, "institution": inst, "field_of_study": field_study,
            "start_date": start, "year_of_completion": end, "final_evaluation_grade": "", "exam": {},
        })
        st.divider()

# ── Experience ────────────────────────────────────────────────────────────────
with st.expander("💼 Work Experience"):
    exp_list = data.get("experience_details", [{}])
    if "exp_count" not in st.session_state:
        st.session_state.exp_count = len(exp_list)
    if st.button("+ Add Experience Entry"):
        st.session_state.exp_count += 1
        exp_list.append({})

    updated_exp = []
    for i in range(st.session_state.exp_count):
        exp = exp_list[i] if i < len(exp_list) else {}
        st.markdown(f"**Position {i+1}**")
        col1, col2 = st.columns(2)
        with col1:
            pos = field("Job Title", exp.get("position", ""), f"exp_pos_{i}")
            company = field("Company", exp.get("company", ""), f"exp_co_{i}")
            period = field("Employment Period", exp.get("employment_period", ""), f"exp_period_{i}",
                           help="e.g. 01/2022 - Present")
        with col2:
            location = st.text_input("Location", exp.get("location", ""), key=f"exp_loc_{i}")
            industry = st.text_input("Industry", exp.get("industry", ""), key=f"exp_ind_{i}")

        responsibilities = st.text_area(
            "Key Responsibilities (one per line)",
            value="\n".join(
                r.get(f"responsibility_{j+1}", "") if isinstance(r, dict) else str(r)
                for j, r in enumerate(exp.get("key_responsibilities", []))
            ),
            key=f"exp_resp_{i}", height=100,
        )
        skills = st.text_input(
            "Skills (comma-separated)",
            value=", ".join(exp.get("skills_acquired", [])),
            key=f"exp_skills_{i}",
        )
        resp_list = [{"responsibility_1": r.strip()} for r in responsibilities.splitlines() if r.strip()]
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        updated_exp.append({
            "position": pos, "company": company, "employment_period": period,
            "location": location, "industry": industry,
            "key_responsibilities": resp_list, "skills_acquired": skill_list,
        })
        st.divider()

# ── Preferences ───────────────────────────────────────────────────────────────
with st.expander("⚙️ Preferences & Availability"):
    wp = data.get("work_preferences", {})
    sal = data.get("salary_expectations", {})
    avail = data.get("availability", {})
    col1, col2 = st.columns(2)
    with col1:
        salary_range = st.text_input("Salary Range (USD)", sal.get("salary_range_usd", ""),
                                     key="pref_salary", help="e.g. 120000 - 180000")
        notice = st.text_input("Notice Period", avail.get("notice_period", "2 weeks"), key="pref_notice")
    with col2:
        remote_work = st.checkbox("Open to Remote", value=wp.get("remote_work", "Yes") == "Yes", key="pref_remote")
        relocation = st.checkbox("Open to Relocation", value=wp.get("open_to_relocation", "No") == "Yes", key="pref_reloc")
        assessments = st.checkbox("Willing to complete assessments",
                                  value=wp.get("willing_to_complete_assessments", "Yes") == "Yes", key="pref_assess")
        bg_checks = st.checkbox("Willing to undergo background checks",
                                value=wp.get("willing_to_undergo_background_checks", "Yes") == "Yes", key="pref_bg")
        drug_tests = st.checkbox("Willing to undergo drug tests",
                                 value=wp.get("willing_to_undergo_drug_tests", "No") == "Yes", key="pref_drug")

# ── Self-ID ───────────────────────────────────────────────────────────────────
with st.expander("🏳️‍🌈 Self-Identification (optional)"):
    sid = data.get("self_identification", {})
    col1, col2 = st.columns(2)
    with col1:
        gender = st.text_input("Gender identity", sid.get("gender", "Non-binary"), key="sid_gender",
                               help="Select 'Non-binary' or 'Prefer not to say' when options allow")
        pronouns = st.text_input("Pronouns", sid.get("pronouns", "Any"), key="sid_pronouns")
        ethnicity = field("Ethnicity", sid.get("ethnicity", ""), "sid_ethnicity",
                          help="'Prefer not to say' is always an option")
    with col2:
        vet_options = ["No", "Yes", "Prefer not to say"]
        veteran = st.selectbox("Veteran status", vet_options,
                               index=vet_options.index(sid.get("veteran", "No")), key="sid_vet")
        dis_options = ["Prefer not to say", "No", "Yes"]
        disability = st.selectbox("Disability disclosure", dis_options,
                                  index=dis_options.index(sid.get("disability", "Prefer not to say")),
                                  key="sid_dis")

st.divider()

# ── Save ──────────────────────────────────────────────────────────────────────
if st.button("💾 Save Resume Profile", type="primary", use_container_width=True):
    data["personal_information"] = {
        **data.get("personal_information", {}),
        "name": name, "surname": surname, "email": email, "phone": phone,
        "city": city, "zip_code": zip_code, "linkedin": linkedin, "date_of_birth": dob,
    }
    data["education_details"] = updated_edu
    data["experience_details"] = updated_exp
    data["salary_expectations"] = {"salary_range_usd": salary_range}
    data["availability"] = {"notice_period": notice}
    data["work_preferences"] = {
        **data.get("work_preferences", {}),
        "remote_work": "Yes" if remote_work else "No",
        "open_to_relocation": "Yes" if relocation else "No",
        "willing_to_complete_assessments": "Yes" if assessments else "No",
        "willing_to_undergo_background_checks": "Yes" if bg_checks else "No",
        "willing_to_undergo_drug_tests": "Yes" if drug_tests else "No",
    }
    data["self_identification"] = {
        "gender": gender, "pronouns": pronouns, "veteran": veteran,
        "disability": disability, "ethnicity": ethnicity,
    }
    RESUME_PATH.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
    st.success("✅ Profile saved!")
    st.balloons()
