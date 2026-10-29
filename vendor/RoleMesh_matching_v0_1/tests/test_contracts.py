import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from rolemesh_matching.integration import run_request, ContractError, load_schema

ROOT = Path(__file__).resolve().parents[1]

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((ROOT / "examples/input.json").read_text(encoding="utf-8"))

    def test_schemas_are_valid_and_packaged_copies_identical(self):
        for name in ("input", "output", "error"):
            Draft202012Validator.check_schema(load_schema(name))
            self.assertEqual(load_schema(name), json.loads((ROOT / f"contracts/{name}.schema.json").read_text(encoding="utf-8")))

    def test_actual_output_validates(self):
        out = run_request(self.request)
        self.assertEqual(out["contract_version"], "0.1.0")
        self.assertEqual([p["match"] for p in out["projects"]], [74, 61])

    def test_required_field_error_has_precise_path(self):
        self.request["profile"].pop("profile_version")
        with self.assertRaises(ContractError) as cm:
            run_request(self.request)
        self.assertIn("$.profile.profile_version", [e["path"] for e in cm.exception.fields])

    def test_unknown_fields_are_rejected_without_echoing_values(self):
        self.request["profile"]["phone"] = "sensitive-personal-data"
        with self.assertRaises(ContractError) as cm:
            run_request(self.request)
        self.assertNotIn("sensitive-personal-data", json.dumps(cm.exception.as_dict()))

    def test_timezone_is_required(self):
        for timestamp in ("2026-10-20T12:00:00", "invalid"):
            self.request["profile"]["availability_reported_at"] = timestamp
            with self.assertRaises(ContractError):
                run_request(self.request)

    def test_business_restrictions_are_not_silently_ignored(self):
        self.request["roles"][0]["language_is_required"] = True
        self.request["roles"][0]["required_languages"] = []
        with self.assertRaises(ContractError) as cm:
            run_request(self.request)
        self.assertEqual(cm.exception.code, "BUSINESS_INPUT_INVALID")

    def test_empty_candidate_list_is_valid_not_an_error(self):
        self.request["roles"] = []
        out = run_request(self.request)
        self.assertEqual(out["recommendations"], [])

    def test_boolean_is_not_numeric_time(self):
        self.request["profile"]["availability_hours_per_week"] = True
        with self.assertRaises(ContractError):
            run_request(self.request)

    def test_model_error_does_not_become_input_or_empty_results(self):
        role = self.request["roles"][0]
        role["project_domains"] = []
        role["raw_fields"] = {"project_domains":"教育科技"}
        self.request["roles"] = [role]
        class BrokenModel:
            def similarity(self, a, b):
                raise RuntimeError("model unavailable")
        with self.assertRaises(RuntimeError):
            run_request(self.request, semantic=BrokenModel())

    def test_contract_fixtures_all_match_expectations(self):
        cases = json.loads((ROOT / "examples/contract_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                if "error_code" in expected:
                    with self.assertRaises(ContractError) as cm:
                        run_request(case["request"])
                    self.assertEqual(cm.exception.code, expected["error_code"])
                    Draft202012Validator(load_schema("error")).validate(cm.exception.as_dict())
                else:
                    row = run_request(case["request"])["comparisons"][0]
                    for key, value in expected.items():
                        self.assertEqual(row[key], value)
