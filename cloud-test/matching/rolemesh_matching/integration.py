"""Versioned backend handoff. JSON Schemas are the shared transport contract."""
import json
import re
from datetime import datetime
from importlib.resources import files

from .engine import recommend, recommend_profiles, _validate

CONTRACT_VERSION = "0.1.0"


class ContractError(ValueError):
    def __init__(self, code, fields):
        super().__init__(code)
        self.code, self.fields = code, fields

    def as_dict(self):
        return {"contract_version": CONTRACT_VERSION, "error": {"code": self.code, "fields": self.fields}}


def load_schema(name):
    if name not in ("input", "output", "error", "profiles-input", "profiles-output", "event"):
        raise ValueError("Unknown contract schema")
    return json.loads(files("rolemesh_matching").joinpath("schemas", name + ".schema.json").read_text(encoding="utf-8"))


def _validate_schema(value, name):
    from jsonschema import Draft202012Validator, FormatChecker
    formats = FormatChecker()

    @formats.checks("date-time")
    def timezone_timestamp(value):
        if not isinstance(value, str):
            return True
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
            return False
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
        except ValueError:
            return False

    validator = Draft202012Validator(load_schema(name), format_checker=formats)
    errors = []
    for error in validator.iter_errors(value):
        path = "$" + "".join(f"[{k}]" if isinstance(k, int) else "." + k for k in error.absolute_path)
        # Do not return raw personal input or full validation exception messages.
        if error.validator == "required":
            absent = [k for k in error.validator_value if k not in error.instance]
            errors.extend({"path": path + "." + k, "rule": "required", "message": "缺少必填字段"} for k in absent)
        else:
            errors.append({"path": path, "rule": error.validator, "message": "字段类型或取值不符合契约"})
    if errors:
        raise ContractError("INPUT_INVALID" if name in ("input", "profiles-input", "event") else "OUTPUT_INVALID", errors)


def run_request(request, *, semantic=None):
    """Kyla calls this function after authorization and database-to-DTO conversion.

    Returns the direct result body, not an HTTP response. ContractError is mapped
    to the backend's existing error envelope; no route or auth scheme is assumed.
    Model failures are allowed to propagate, never disguised as 'no match'.
    """
    _validate_schema(request, "input")
    try:
        ids = [role["role_id"] for role in request["roles"]]
        if len(ids) != len(set(ids)):
            raise ValueError("role_id must be unique across the request")
        for role in request["roles"]:
            _validate(request["profile"], role)
    except ValueError as error:
        raise ContractError("BUSINESS_INPUT_INVALID", [{"path": "$", "rule": "business", "message": str(error)}]) from error
    result = recommend(request["profile"], request["roles"], semantic=semantic)
    result["contract_version"] = CONTRACT_VERSION
    _validate_schema(result, "output")
    return result


def run_profiles_request(request, *, semantic=None):
    """Validated Role-to-profiles transport; original DTOs and error envelope."""
    _validate_schema(request, "profiles-input")
    try:
        ids = [profile["profile_id"] for profile in request["profiles"]]
        if len(ids) != len(set(ids)):
            raise ValueError("profile_id must be unique across the request")
        _validate({"profile_id": "validation-only", "profile_version": 1}, request["role"])
        for profile in request["profiles"]:
            _validate(profile, request["role"])
    except ValueError as error:
        raise ContractError("BUSINESS_INPUT_INVALID", [{"path": "$", "rule": "business", "message": str(error)}]) from error
    result = recommend_profiles(request["role"], request["profiles"], semantic=semantic)
    result["contract_version"] = CONTRACT_VERSION
    _validate_schema(result, "profiles-output")
    return result
