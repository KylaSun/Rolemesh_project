import copy
import json
import math
from pathlib import Path
import unittest

from rolemesh_matching import calculate_weights, match_role, recommend
from rolemesh_matching.semantic import to_score

ROOT = Path(__file__).resolve().parents[1]


class MatchingTests(unittest.TestCase):
    def setUp(self):
        data = json.loads((ROOT / "examples/input.json").read_text(encoding="utf-8"))
        self.p = data["profile"]
        self.r = data["roles"][0]

    def test_all_hard_conditions_pass(self):
        result = match_role(self.p, self.r)
        self.assertEqual(result["eligibility"], "eligible")
        self.assertEqual(result["scoring_status"], "complete")
        self.assertTrue(0 <= result["match"] <= 100)

    def test_expected_component_scores_and_total(self):
        out = match_role(self.p, self.r)
        values = {k: v["score"] for k, v in out["component_scores"].items()}
        self.assertEqual(values, {"skills": 50, "role": 100, "domain": 100, "time": 75})
        self.assertEqual(out["match"], 74)

    def test_missing_soft_item_cannot_enter_formal_recommendations(self):
        self.p.pop("intended_roles")
        self.p["primary_role"] = None
        out = recommend(self.p, [self.r])
        self.assertEqual(out["recommendations"], [])
        self.assertEqual(out["projects"], [])
        self.assertEqual(out["comparisons"][0]["scoring_status"], "provisional")

    def test_missing_required_skill_fails(self):
        self.p["skills"] = []
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")

    def test_unconfirmed_skill_normalization_is_unknown(self):
        self.p["skills"] = []
        self.p["field_status"] = {"skills": "unknown"}
        result = match_role(self.p, self.r)
        self.assertEqual(result["eligibility"], "needs_confirmation")
        self.assertIsNone(result["match"])

    def test_unknown_required_level_is_not_failure(self):
        self.p["skills"][0]["level"] = None
        self.r["required_skills"][0]["min_level"] = 3
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "needs_confirmation")

    def test_insufficient_time_fails(self):
        self.p["availability_hours_per_week"] = 2
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")

    def test_zero_time_is_not_unknown(self):
        self.p["availability_hours_per_week"] = 0
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")

    def test_unknown_time_is_unknown(self):
        self.p["availability_hours_per_week"] = None
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "needs_confirmation")

    def test_time_score_capped(self):
        self.p["availability_hours_per_week"] = 168
        self.assertEqual(match_role(self.p, self.r)["component_scores"]["time"]["score"], 100)

    def test_domain_no_preference_is_not_full_score(self):
        self.p["domain_preference_any"] = True
        d = match_role(self.p, self.r)
        self.assertIsNone(d["component_scores"]["domain"]["score"])
        self.assertNotIn("domain", d["effective_weights"])
        self.assertAlmostEqual(sum(d["effective_weights"].values()), 1)

    def test_language_any_and_all_differ(self):
        self.r.update(language_is_required=True, required_languages=["zh", "en"], language_requirement_mode="any")
        self.p["languages"] = ["zh"]
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "eligible")
        self.r["language_requirement_mode"] = "all"
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")

    def test_unknown_language_not_known_absence(self):
        self.r.update(language_is_required=True, required_languages=["en"])
        self.p["field_status"] = {"languages": "unknown"}
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "needs_confirmation")

    def test_collaboration_any(self):
        self.r.update(collaboration_is_required=True, allowed_collaboration_modes=["in_person"])
        self.p["collaboration_any"] = True
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "eligible")

    def test_academic_year_restriction(self):
        self.r["allowed_academic_years"] = ["year.4"]
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")

    def test_closed_and_full_excluded(self):
        for state in ("closed", "paused", "full"):
            self.r["recruitment_status"] = state
            self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")
        self.r.update(recruitment_status="open", openings_remaining=0)
        self.assertEqual(match_role(self.p, self.r)["eligibility"], "ineligible")

    def test_missing_soft_level_is_not_formal_score(self):
        self.r["preferred_skills"][0]["min_level"] = 4
        self.p["skills"][1]["level"] = None
        result = match_role(self.p, self.r)
        self.assertEqual(result["eligibility"], "eligible")
        self.assertEqual(result["scoring_status"], "provisional")
        self.assertIsNone(result["match"])
        self.assertLess(result["scoring_coverage"], 1)

    def test_preferred_absent_not_eliminated(self):
        self.p["skills"] = self.p["skills"][:1]
        result = match_role(self.p, self.r)
        self.assertEqual(result["eligibility"], "eligible")
        self.assertEqual(result["component_scores"]["skills"]["score"], 0)

    def test_no_configured_skills_not_automatic_full_score(self):
        self.r["preferred_skills"] = []
        result = match_role(self.p, self.r)
        self.assertNotIn("skills", result["effective_weights"])

    def test_validation_rejects_bad_types(self):
        for value in (True, "8", -1, 169, float("nan"), float("inf")):
            self.p["availability_hours_per_week"] = value
            with self.assertRaises(ValueError):
                match_role(self.p, self.r)

    def test_duplicate_skill_and_empty_required_language_rejected(self):
        p = copy.deepcopy(self.p)
        p["skills"].append(p["skills"][0])
        with self.assertRaises(ValueError):
            match_role(p, self.r)
        self.r.update(language_is_required=True, required_languages=[])
        with self.assertRaises(ValueError):
            match_role(self.p, self.r)

    def test_unsupported_restriction_rejected(self):
        self.r["start_within_days"] = 7
        with self.assertRaises(ValueError):
            match_role(self.p, self.r)

    def test_no_mutation_and_no_contact_data_returned(self):
        self.p["phone"] = "private"
        before = copy.deepcopy(self.p)
        out = recommend(self.p, [self.r])
        self.assertEqual(before, self.p)
        self.assertNotIn("private", json.dumps(out))

    def test_updated_version_and_time_recorded(self):
        self.p["profile_version"] = 8
        out = match_role(self.p, self.r)
        self.assertEqual(out["profile_version"], 8)
        self.assertTrue(out["computed_at"].endswith("+00:00"))

    def test_project_aggregation_and_stable_ties(self):
        other = copy.deepcopy(self.r)
        other["role_id"] = "r000"
        out = recommend(self.p, [self.r, other])
        self.assertEqual(len(out["projects"]), 1)
        self.assertEqual(out["projects"][0]["best_role_id"], "r000")

    def test_duplicate_role_ids_rejected(self):
        with self.assertRaises(ValueError):
            recommend(self.p, [self.r, self.r])

    def test_ahp_reciprocity_and_consistency(self):
        ahp = calculate_weights()
        self.assertAlmostEqual(sum(ahp["weights"].values()), 1)
        self.assertLess(ahp["CR"], .1)
        with self.assertRaises(ValueError):
            calculate_weights([[1] * 4] * 3)

    def test_no_model_does_not_fake_semantics(self):
        self.r["project_domains"] = []
        self.r["raw_fields"] = {"project_domains": "校园教育"}
        self.p["raw_fields"] = {"field": "学习工具"}
        out = match_role(self.p, self.r)
        self.assertIsNone(out["match"])
        self.assertIn("semantic_model_not_loaded", out["warnings"])

    def test_semantic_adapter_and_negation_guard(self):
        class Stub:
            model_id, revision = "test-stub-not-real-gte", "test"
            def similarity(self, left, right):
                return .6
        self.r["project_domains"] = []
        self.r["raw_fields"] = {"project_domains": "教育科技"}
        self.p["raw_fields"] = {"field": "校园学习工具"}
        out = match_role(self.p, self.r, semantic=Stub())
        self.assertAlmostEqual(out["component_scores"]["domain"]["score"], 50)
        self.p["raw_fields"]["field"] = "不懂教育科技"
        out = match_role(self.p, self.r, semantic=Stub())
        self.assertIsNone(out["match"])
        self.assertIn("semantic_text_needs_confirmation", out["warnings"])

    def test_semantic_scaling_bounds(self):
        self.assertEqual(to_score(-.2), 0)
        self.assertEqual(to_score(.9), 100)
        with self.assertRaises(ValueError):
            to_score(math.nan)


if __name__ == "__main__":
    unittest.main()
