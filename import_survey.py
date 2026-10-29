"""Import consented formal survey profiles into the local SQLite dev database.

Only matching/profile answers are imported. Full name, WeChat ID, timestamps,
IP, user-agent, referrer, and other technical metadata are deliberately omitted.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from database import DB_PATH, get_connection, init_db

CONSENT_HEADER = "1.【必填｜单选】"
PREFERRED_NAME_HEADER = "3.【必填｜填空】"
ACADEMIC_YEAR_HEADER = "5.【必填｜单选】"
MAJOR_HEADER = "6.【必填｜填空】"
STRONGEST_SKILL_HEADER = "8.【必填｜单选】"
STRONGEST_LEVEL_HEADER = "9.【条件必填｜单选】"
EXPERIENCE_LEVEL_HEADER = "10.【必填｜单选】"
EXPERIENCE_SUMMARY_HEADER = "11.【选填｜简短填空】"
PRIMARY_ROLE_HEADER = "13.【必填｜单选】"
GOAL_HEADER = "15.【必填｜单选】"
PROJECT_STATUS_HEADER = "17.【必填｜单选】"
PROJECT_IDEA_HEADER = "18.【条件选填｜简短填空】"
HOURS_HEADER = "19.【必填｜数字填空】"
START_HEADER = "20.【必填｜单选】"
INVITATION_HEADER = "23.【必填｜单选】"
VISIBILITY_HEADER = "24.【必填｜单选】"

# Only labels already present in the shared V0.1 seed codebook are normalized.
KNOWN_SKILLS = {"Python": "skill.python"}
KNOWN_ROLES = {"前端开发": "role.frontend", "AI与算法开发": "role.algorithm"}
KNOWN_DOMAINS = {"教育科技": "domain.education"}
KNOWN_LANGUAGES = {"中文": "zh", "英语": "en"}
KNOWN_MODES = {"线上远程": "remote", "线下合作": "in_person", "线上线下结合": "hybrid"}


def header(headers: list[str], prefix: str) -> str:
    matches = [h for h in headers if h.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"Expected one CSV header starting with {prefix!r}, found {len(matches)}")
    return matches[0]


def clean_option(value: str) -> str:
    value = value.strip()
    return re.sub(r"^[A-Z]{1,2}\.", "", value).strip()


def selected_group(row: dict[str, str], headers: list[str], number: str) -> list[str]:
    cols = [h for h in headers if h.startswith(number + ".") and ":" in h]
    result = []
    for col in cols:
        value = (row.get(col) or "").strip()
        if value:
            result.append(clean_option(value))
    return result


def group_fully_mapped(labels: list[str], mapping: dict[str, str]) -> bool:
    return all(label.split(" / ", 1)[0].strip() in mapping for label in labels)


def mapped(labels: list[str], mapping: dict[str, str]) -> list[str]:
    output = []
    for label in labels:
        code = mapping.get(label.split(" / ", 1)[0].strip())
        if code and code not in output:
            output.append(code)
    return output


def answer(row: dict[str, str], headers: list[str], prefix: str) -> str:
    return (row.get(header(headers, prefix)) or "").strip()


def nonempty_group_values(row: dict[str, str], headers: list[str], number: str) -> dict[str, str]:
    output = {}
    for col in headers:
        if col.startswith(number + ".") and ":" in col:
            value = (row.get(col) or "").strip()
            if value:
                label = col.split(":", 1)[1].strip()
                if "[选项填空]" in label:
                    output["other_write_in"] = value
    return output


def record_to_rows(row: dict[str, str], headers: list[str]) -> tuple[tuple, tuple, tuple, dict]:
    record_id = (row.get("编号") or "").strip()
    if not record_id.isdigit():
        raise ValueError("A survey row has no numeric 编号")
    consent = answer(row, headers, CONSENT_HEADER)
    if "同意" not in consent or "Agree" not in consent:
        raise ValueError(f"Survey record {record_id} has no affirmative consent")

    nickname = answer(row, headers, PREFERRED_NAME_HEADER)
    if not nickname:
        raise ValueError(f"Survey record {record_id} has no display nickname")

    skill_labels = selected_group(row, headers, "7")
    role_labels = selected_group(row, headers, "12")
    domain_labels = selected_group(row, headers, "14")
    project_type_labels = selected_group(row, headers, "16")
    collaboration_labels = selected_group(row, headers, "21")
    language_labels = selected_group(row, headers, "22")

    strongest = clean_option(answer(row, headers, STRONGEST_SKILL_HEADER))
    level_answer = clean_option(answer(row, headers, STRONGEST_LEVEL_HEADER))
    level_match = re.search(r"\bL([1-5])\b", level_answer)
    strongest_level = int(level_match.group(1)) if level_match else None
    strongest_label = strongest.split(" / ", 1)[0].strip()

    skills = []
    partial_skills = False
    for label in skill_labels:
        label_zh = label.split(" / ", 1)[0].strip()
        code = KNOWN_SKILLS.get(label_zh)
        if code:
            level = strongest_level if label_zh == strongest_label else None
            skills.append({"skill_code": code, "level": level, "assessment_source": "self_reported"})
        else:
            partial_skills = True
    skills_known = not partial_skills and bool(skill_labels)
    # A strongest skill is only a level assessment for that one skill.
    if strongest_label not in KNOWN_SKILLS:
        skills_known = False

    intended_roles = mapped(role_labels, KNOWN_ROLES)
    roles_known = bool(role_labels) and group_fully_mapped(role_labels, KNOWN_ROLES)
    primary_label = clean_option(answer(row, headers, PRIMARY_ROLE_HEADER)).split(" / ", 1)[0].strip()
    primary_role = KNOWN_ROLES.get(primary_label)
    if primary_role and primary_role not in intended_roles:
        primary_role = None
        roles_known = False

    domain_any = any("暂无明确偏好" in x or "Open to All" in x for x in domain_labels)
    domain_specific = [x for x in domain_labels if "暂无明确偏好" not in x and "Open to All" not in x]
    domain_codes = mapped(domain_specific, KNOWN_DOMAINS)
    domains_known = domain_any or (bool(domain_specific) and group_fully_mapped(domain_specific, KNOWN_DOMAINS))

    collaboration_any = any("均可接受" in x or "Any Format" in x for x in collaboration_labels)
    collaboration_specific = [x for x in collaboration_labels if "均可接受" not in x and "Any Format" not in x]
    collaboration_codes = mapped(collaboration_specific, KNOWN_MODES)
    collaboration_known = collaboration_any or (bool(collaboration_specific) and group_fully_mapped(collaboration_specific, KNOWN_MODES))

    language_codes = mapped(language_labels, KNOWN_LANGUAGES)
    languages_known = bool(language_labels) and group_fully_mapped(language_labels, KNOWN_LANGUAGES)

    hours_text = answer(row, headers, HOURS_HEADER).strip().replace("\t", "").replace(",", ".")
    try:
        hours = float(hours_text)
    except ValueError as exc:
        raise ValueError(f"Survey record {record_id} has invalid weekly hours") from exc
    if not 0 <= hours <= 168:
        raise ValueError(f"Survey record {record_id} has out-of-range weekly hours")

    academic_raw = clean_option(answer(row, headers, ACADEMIC_YEAR_HEADER))
    academic_zh = academic_raw.split(" / ", 1)[0].strip()
    academic_map = {"大一": "year.1", "大二": "year.2", "大三": "year.3", "大四": "year.4", "研究生": "year.postgraduate"}
    academic_year = academic_map.get(academic_zh)

    experience_summary = answer(row, headers, EXPERIENCE_SUMMARY_HEADER)
    visibility_answer = clean_option(answer(row, headers, VISIBILITY_HEADER))
    if "仅自己" in visibility_answer or "Private" in visibility_answer:
        visibility = "private"
        visibility_preference = "private"
        selected_experience_visible = False
    elif "本人主动选择公开的项目经历" in visibility_answer or "Selected Experience" in visibility_answer:
        visibility = "basic_card"
        visibility_preference = "basic_card_with_selected_experience"
        selected_experience_visible = True
    else:
        visibility = "basic_card"
        visibility_preference = "basic_card"
        selected_experience_visible = False

    invitation = clean_option(answer(row, headers, INVITATION_HEADER))
    raw_fields = {
        "skills": skill_labels,
        "role": "；".join(role_labels),
        "coop": "；".join(collaboration_labels),
        "time": hours_text,
    }
    profiles = {
        "profile_id": f"profile.survey.{int(record_id):03d}",
        "profile_version": 1,
        "academic_year": academic_year,
        "major": answer(row, headers, MAJOR_HEADER) or None,
        "intended_major": None,
        "skills": skills,
        "intended_roles": intended_roles,
        "primary_role": primary_role,
        "domain_interests": domain_codes,
        "domain_preference_any": domain_any,
        "experience_level": clean_option(answer(row, headers, EXPERIENCE_LEVEL_HEADER)) or None,
        "experience_summary": experience_summary if selected_experience_visible else None,
        "availability_hours_per_week": hours,
        "available_from": clean_option(answer(row, headers, START_HEADER)) or None,
        "availability_reported_at": None,
        "collaboration_modes": collaboration_codes,
        "collaboration_any": collaboration_any,
        "languages": language_codes,
        "field_status": {
            "skills": "provided" if skills_known else "unknown",
            "intended_roles": "provided" if roles_known else "unknown",
            "domain_interests": "provided" if domains_known else "unknown",
            "collaboration_modes": "provided" if collaboration_known else "unknown",
            "languages": "provided" if languages_known else "unknown",
            "availability_hours_per_week": "provided",
        },
        "raw_fields": raw_fields,
    }
    details = {
        "survey_responses": {
            "strongest_skill": strongest,
            "strongest_skill_level": level_answer,
            "preferred_roles": role_labels,
            "preferred_domains": domain_labels,
            "project_goal": clean_option(answer(row, headers, GOAL_HEADER)),
            "preferred_project_types": project_type_labels,
            "project_status": clean_option(answer(row, headers, PROJECT_STATUS_HEADER)),
            "project_idea_and_missing_roles": answer(row, headers, PROJECT_IDEA_HEADER) or None,
            "available_from": clean_option(answer(row, headers, START_HEADER)),
            "collaboration_preferences": collaboration_labels,
            "languages": language_labels,
            "matching_invitation_preference": invitation,
            "visibility_preference": visibility_preference,
            "selected_experience_visible": selected_experience_visible,
            "other_role_write_in": nonempty_group_values(row, headers, "12").get("other_write_in"),
            "other_domain_write_in": nonempty_group_values(row, headers, "14").get("other_write_in"),
            "other_language_write_in": nonempty_group_values(row, headers, "22").get("other_write_in"),
        },
    }
    now = datetime.now(timezone.utc).isoformat()
    user_id = f"user.survey.{int(record_id):03d}"
    users_tuple = (user_id, nickname, now)
    profile_tuple = (profiles["profile_id"], user_id, 1, json.dumps(profiles, ensure_ascii=False), visibility, now)
    details_tuple = (profiles["profile_id"], int(record_id), json.dumps(details, ensure_ascii=False), now)
    return users_tuple, profile_tuple, details_tuple, profiles


def import_csv(path: Path, *, dry_run: bool = False) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if not headers or "编号" not in headers:
            raise ValueError("CSV is missing required headers")
        rows = list(reader)

    prepared = [record_to_rows(row, headers) for row in rows]
    record_ids = [row[2][1] for row in prepared]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("Duplicate survey record IDs found; nothing imported")

    if dry_run:
        return {"rows": len(prepared), "consented": len(prepared), "dry_run": True}

    init_db()
    connection = get_connection()
    inserted_users = inserted_profiles = skipped = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        for user_row, profile_row, details_row, profile in prepared:
            existing = connection.execute(
                "SELECT user_id, profile_json FROM talent_profiles WHERE profile_id = ?",
                (profile_row[0],),
            ).fetchone()
            if existing:
                prior = json.loads(existing["profile_json"])
                if existing["user_id"] != user_row[0] or prior.get("survey_record_id") != details_row[1]:
                    raise ValueError(f"Profile ID collision for {profile_row[0]}; nothing committed")
                # Rewrite this import's initial draft as the strict matching
                # DTO and keep survey-only answers in their own table.
                connection.execute(
                    "UPDATE talent_profiles SET profile_json = ?, visibility = ?, updated_at = ? WHERE profile_id = ?",
                    (profile_row[3], profile_row[4], profile_row[5], profile_row[0]),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO survey_profile_details (profile_id, source_record_id, details_json, imported_at) VALUES (?, ?, ?, ?)",
                    details_row,
                )
                skipped += 1
                continue
            existing_user = connection.execute("SELECT user_id FROM users WHERE user_id = ?", (user_row[0],)).fetchone()
            if existing_user:
                raise ValueError(f"User ID collision for {user_row[0]} without matching imported profile; nothing committed")
            connection.execute("INSERT INTO users (user_id, display_name, created_at) VALUES (?, ?, ?)", user_row)
            inserted_users += 1
            connection.execute(
                "INSERT INTO talent_profiles (profile_id, user_id, profile_version, profile_json, visibility, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                profile_row,
            )
            connection.execute(
                "INSERT INTO survey_profile_details (profile_id, source_record_id, details_json, imported_at) VALUES (?, ?, ?, ?)",
                details_row,
            )
            inserted_profiles += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "rows": len(prepared),
        "consented": len(prepared),
        "inserted_users": inserted_users,
        "inserted_profiles": inserted_profiles,
        "skipped_already_imported": skipped,
        "db_path": str(DB_PATH),
        "dry_run": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import consented RoleMesh survey profiles to the local SQLite database")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to SQLite")
    args = parser.parse_args()
    print(json.dumps(import_csv(args.csv_path, dry_run=args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
