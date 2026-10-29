"""Rules + computed AHP weights + optional GTE soft-text comparison.

All calls are read-only. Authorization and candidate filtering belong to the backend.
Unknown data never becomes an inferred skill or a hard-condition pass.
"""
import math
from datetime import datetime, timezone

from .ahp import calculate_weights
from .semantic import to_score

VERSION = "0.1.0-draft"
WEIGHTS = calculate_weights()["weights"]
LABELS = {"skills": "加分技能", "role": "角色意向", "domain": "领域兴趣", "time": "期望时间"}
MODES = {"remote", "in_person", "hybrid"}
PROFILE_LISTS = ("intended_roles", "domain_interests", "collaboration_modes", "languages")
ROLE_LISTS = ("project_domains", "allowed_collaboration_modes", "required_languages", "allowed_academic_years", "allowed_major_codes")


def _number(value, path, low=0, high=168, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path}: expected finite number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{path}: expected integer")
    if not low <= value <= high:
        raise ValueError(f"{path}: expected {low}..{high}")


def _strings(value, path):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{path}: expected non-empty string items in an array")
    if len(value) != len(set(value)):
        raise ValueError(f"{path}: duplicate items")


def _known(profile, key):
    return key in profile and profile[key] is not None and profile.get("field_status", {}).get(key) != "unknown"


def _validate(profile, role):
    if not isinstance(profile, dict) or not isinstance(role, dict):
        raise ValueError("profile and role must be objects")
    for obj, prefix, ids in ((profile, "profile", ("profile_id",)), (role, "role", ("project_id", "role_id", "role_code"))):
        for key in ids:
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                raise ValueError(f"{prefix}.{key}: required string")
        key = "profile_version" if prefix == "profile" else "role_version"
        _number(obj.get(key), f"{prefix}.{key}", 1, 2**53 - 1, True)
    for key in PROFILE_LISTS:
        if key in profile:
            _strings(profile[key], f"profile.{key}")
    for key in ROLE_LISTS:
        if key not in role:
            raise ValueError(f"role.{key}: required, use [] when no restriction")
        _strings(role[key], f"role.{key}")
    for obj, keys in ((profile, ("domain_preference_any", "collaboration_any")), (role, ("collaboration_is_required", "language_is_required"))):
        for key in keys:
            if key in obj and not isinstance(obj[key], bool):
                raise ValueError(f"{key}: expected boolean")
            if obj is role and key not in obj:
                raise ValueError(f"role.{key}: required boolean")
    for key in ("academic_year", "major", "intended_major", "experience_level", "experience_summary", "available_from", "availability_reported_at", "primary_role"):
        if profile.get(key) is not None and not isinstance(profile[key], str):
            raise ValueError(f"profile.{key}: expected string or null")
    if profile.get("primary_role") and profile["primary_role"] not in profile.get("intended_roles", []):
        raise ValueError("primary_role must belong to intended_roles")
    if set(profile.get("collaboration_modes", [])) - MODES or set(role["allowed_collaboration_modes"]) - MODES:
        raise ValueError("Invalid collaboration mode")
    status = profile.get("field_status", {})
    if not isinstance(status, dict) or any(v not in ("provided", "unknown") for v in status.values()):
        raise ValueError("field_status values must be provided or unknown")
    if role.get("recruitment_status") not in ("open", "paused", "closed", "full"):
        raise ValueError("Invalid or missing recruitment_status")
    _number(role.get("openings_remaining"), "openings_remaining", 0, 2**31 - 1, True)
    if role.get("language_requirement_mode") not in ("any", "all"):
        raise ValueError("language_requirement_mode must be any or all")
    for key in ("min_hours_per_week", "preferred_hours_per_week"):
        if key not in role:
            raise ValueError(f"role.{key}: required number or null")
        if role[key] is not None:
            _number(role[key], key)
    if profile.get("availability_hours_per_week") is not None:
        _number(profile["availability_hours_per_week"], "availability_hours_per_week")
    if role["min_hours_per_week"] is not None and role["preferred_hours_per_week"] is not None and role["preferred_hours_per_week"] < role["min_hours_per_week"]:
        raise ValueError("preferred hours cannot be below minimum hours")
    # Do not silently ignore requirements that this version cannot evaluate.
    if role.get("start_within_days") is not None or role["allowed_major_codes"]:
        raise ValueError("V0.1 does not enable start date or major restrictions")
    for enabled, key in (("language_is_required", "required_languages"), ("collaboration_is_required", "allowed_collaboration_modes")):
        if role[enabled] and not role[key]:
            raise ValueError(f"{enabled} is enabled but {key} is empty")
    for obj, key, level_key in ((profile, "skills", "level"), (role, "required_skills", "min_level"), (role, "preferred_skills", "min_level")):
        if obj is role and key not in obj:
            raise ValueError(f"role.{key}: required array")
        items = obj.get(key, [])
        if not isinstance(items, list):
            raise ValueError(f"{key}: expected array")
        codes = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("skill_code"), str) or not item["skill_code"].strip():
                raise ValueError(f"{key}: each item requires skill_code")
            codes.append(item["skill_code"])
            if item.get(level_key) is not None:
                _number(item[level_key], f"{key}.{level_key}", 1, 5, True)
            if obj is profile and (not isinstance(item.get("assessment_source"), str) or not item["assessment_source"]):
                raise ValueError("skills.assessment_source: required string")
        if len(codes) != len(set(codes)):
            raise ValueError(f"{key}: duplicate skill codes")
    if {x["skill_code"] for x in role["required_skills"]} & {x["skill_code"] for x in role["preferred_skills"]}:
        raise ValueError("A skill cannot be both required and preferred")
    for obj in (profile, role):
        raw = obj.get("raw_fields", {})
        if not isinstance(raw, dict):
            raise ValueError("raw_fields must be an object")
        for key, value in raw.items():
            if key in ("skills", "preferred_skills"):
                _strings(value, f"raw_fields.{key}")
            elif not isinstance(value, str):
                raise ValueError(f"raw_fields.{key}: expected string")


def _entry(code, label, text):
    return {"code": code, "label": label, "text": text}


def _ambiguous(text):
    # A conservative heuristic, NOT a complete negation/ability parser.
    lowered = text.lower()
    return any(x in lowered for x in ("不会", "不懂", "想学", "希望学习", "没有", "not ", "don't", "want to learn", "no experience"))


def match_role(profile, role, *, semantic=None):
    """Return one comparison. semantic=None never downloads a model.

    Semantic scores use raw_fields extensions only for soft criteria. The backend
    must mark unconfirmed skill normalization as field_status.skills='unknown'.
    """
    _validate(profile, role)
    missing, failed, hard, reasons, warnings = [], [], [], [], []

    def check(code, passed, text, field=None):
        state = "unknown" if passed is None else "pass" if passed else "fail"
        hard.append({"code": code, "status": state, "text": text})
        if passed is None:
            missing.append(field or code)
        elif not passed:
            failed.append(_entry(code, "未满足条件", text))
        else:
            reasons.append(_entry(code, "条件满足", text))

    check("recruitment", role["recruitment_status"] == "open" and role["openings_remaining"] > 0, "岗位需开放且有剩余名额")
    own = {x["skill_code"]: x for x in profile.get("skills", [])}
    for req in role["required_skills"]:
        code, level = req["skill_code"], req.get("min_level")
        mine = own.get(code)
        field = "skills" if not _known(profile, "skills") else f"skills.{code}.level"
        if not _known(profile, "skills"):
            passed = None
        elif mine is None:
            passed = False
        elif level is None:
            passed = True
        else:
            passed = None if mine.get("level") is None else mine["level"] >= level
        check(f"required:{code}", passed, f"必需技能 {code}" + (f"，最低等级 {level}" if level is not None else ""), field)
    minimum = role["min_hours_per_week"]
    if minimum is not None:
        passed = None if not _known(profile, "availability_hours_per_week") else profile["availability_hours_per_week"] >= minimum
        check("min_time", passed, f"每周最低投入 {minimum:g} 小时", "availability_hours_per_week")
    if role["collaboration_is_required"]:
        if profile.get("collaboration_any"):
            passed = True
        elif not _known(profile, "collaboration_modes"):
            passed = None
        else:
            passed = bool(set(profile["collaboration_modes"]) & set(role["allowed_collaboration_modes"]))
        check("collaboration", passed, "协作方式至少有一项双方接受", "collaboration_modes")
    if role["language_is_required"]:
        if not _known(profile, "languages"):
            passed = None
        else:
            flags = [x in profile["languages"] for x in role["required_languages"]]
            passed = any(flags) if role["language_requirement_mode"] == "any" else all(flags)
        check("language", passed, "语言要求：" + role["language_requirement_mode"], "languages")
    if role["allowed_academic_years"]:
        passed = None if not _known(profile, "academic_year") else profile["academic_year"] in role["allowed_academic_years"]
        check("academic_year", passed, "需满足岗位年级范围", "academic_year")

    eligibility = "ineligible" if failed else "needs_confirmation" if missing else "eligible"
    details = {key: {"status": "not_configured", "score": None, "method": None} for key in WEIGHTS}

    def score(key, value, method, text):
        details[key] = {"status": "scored" if value is not None else "missing", "score": None if value is None else round(value, 4), "method": method}
        if value is None:
            missing.append(key)
        elif value > 0:
            reasons.append(_entry(f"score:{key}", LABELS[key], text))

    def semantic_score(key, user_texts, targets):
        if not user_texts:
            score(key, None, "semantic", "")
            return
        if semantic is None:
            warnings.append("semantic_model_not_loaded")
            score(key, None, "semantic", "")
            return
        if any(_ambiguous(x) for x in user_texts + targets):
            warnings.append("semantic_text_needs_confirmation")
            score(key, None, "semantic", "")
            return
        values = [to_score(max(semantic.similarity(u, t) for u in user_texts)) for t in targets]
        score(key, sum(values) / len(values), "semantic", "自由文本语义相关，仅作软性评分，不代表能力核验")
        warnings.append("semantic_thresholds_uncalibrated")

    if eligibility == "eligible":
        if role["preferred_skills"]:
            values = []
            for req in role["preferred_skills"]:
                mine, level = own.get(req["skill_code"]), req.get("min_level")
                if not _known(profile, "skills") or (mine and level is not None and mine.get("level") is None):
                    missing.append(f"skills.{req['skill_code']}")
                    values.append(None)
                elif mine is None:
                    values.append(0.0)
                elif level is None:
                    values.append(100.0)
                else:
                    values.append(100 * min(mine["level"] / level, 1))
            # Incomplete skill subitems make the whole skill criterion provisional.
            value = None if None in values else sum(values) / len(values)
            score("skills", value, "codes_and_levels", "已登记的加分技能满足情况")
        elif role.get("raw_fields", {}).get("preferred_skills"):
            semantic_score("skills", profile.get("raw_fields", {}).get("skills", []), role["raw_fields"]["preferred_skills"])

        if not _known(profile, "intended_roles"):
            score("role", None, "codes", "")
        else:
            value = 100.0 if profile.get("primary_role") == role["role_code"] else 80.0 if role["role_code"] in profile["intended_roles"] else 0.0
            score("role", value, "codes", "命中首选角色" if value == 100 else "命中意向角色")

        if profile.get("domain_preference_any"):
            details["domain"]["status"] = "no_preference"
        elif role["project_domains"]:
            if not _known(profile, "domain_interests"):
                score("domain", None, "codes", "")
            else:
                value = 100 * len(set(profile["domain_interests"]) & set(role["project_domains"])) / len(role["project_domains"])
                score("domain", value, "codes", "领域代码存在共同项")
        elif role.get("raw_fields", {}).get("project_domains"):
            user_text = profile.get("raw_fields", {}).get("field", "")
            semantic_score("domain", [user_text] if user_text.strip() else [], [role["raw_fields"]["project_domains"]])

        preferred = role["preferred_hours_per_week"]
        if preferred is not None and preferred > 0:
            value = None if not _known(profile, "availability_hours_per_week") else 100 * min(profile["availability_hours_per_week"] / preferred, 1)
            score("time", value, "hours_ratio", f"按每周期望投入 {preferred:g} 小时比较，达标即封顶")

    applicable = [k for k, d in details.items() if d["status"] not in ("not_configured", "no_preference")]
    available = [k for k in applicable if details[k]["status"] == "scored"]
    denominator = sum(WEIGHTS[k] for k in applicable)
    usable = sum(WEIGHTS[k] for k in available)
    coverage = usable / denominator if denominator else 0.0
    partial = sum(WEIGHTS[k] * details[k]["score"] for k in available) / usable if usable else None
    complete = bool(applicable) and len(available) == len(applicable)
    formal = partial if eligibility == "eligible" and complete else None
    # Missing soft data does not make an otherwise eligible profile ineligible.
    scoring_status = "complete" if formal is not None else "not_scored" if eligibility != "eligible" else "insufficient_data" if not available else "provisional"
    return {
        "profile_id": profile["profile_id"], "project_id": role["project_id"], "role_id": role["role_id"],
        "eligibility": eligibility, "match": None if formal is None else int(math.floor(formal + 0.5)),
        "provisional_match": None if partial is None or formal is not None else round(partial, 2),
        "scoring_status": scoring_status, "scoring_coverage": round(coverage, 4),
        "component_scores": details, "effective_weights": {k: WEIGHTS[k] / usable for k in available} if usable else {},
        "reasons": reasons, "unmet_requirements": failed, "missing_fields": sorted(set(missing)),
        "hard_checks": hard, "warnings": sorted(set(warnings)),
        "profile_version": profile["profile_version"], "role_version": role["role_version"],
        "algorithm_version": VERSION,
        "model_id": getattr(semantic, "model_id", None), "model_revision": getattr(semantic, "revision", None),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def recommend(profile, roles, *, semantic=None):
    """Compare one profile against many roles, then choose each project's best role.

    Backend must supply only authorized candidates. One invalid role rejects the
    request explicitly instead of silently omitting it. No profile text is returned.
    """
    if not isinstance(roles, list):
        raise ValueError("roles must be an array")
    ids = [r.get("role_id") for r in roles if isinstance(r, dict)]
    if len(ids) != len(set(ids)):
        raise ValueError("role_id must be unique across the request")
    comparisons = [match_role(profile, role, semantic=semantic) for role in roles]

    def sort_key(result):
        def component(key):
            value = result["component_scores"][key]["score"]
            return -1 if value is None else value
        return (-result["match"], -component("skills"), -component("role"), result["role_id"])

    ranked = sorted((x for x in comparisons if x["match"] is not None), key=sort_key)
    best = {}
    for result in ranked:
        best.setdefault(result["project_id"], result)
    projects = [{"project_id": pid, "best_role_id": r["role_id"], "match": r["match"], "reasons": r["reasons"]} for pid, r in best.items()]
    return {"recommendations": ranked, "projects": projects, "comparisons": comparisons, "algorithm_version": VERSION}
