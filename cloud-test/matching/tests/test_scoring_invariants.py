import copy
import json
import unittest
from pathlib import Path
from rolemesh_matching import calculate_weights, match_role

ROOT=Path(__file__).resolve().parents[1]


class ScoringInvariantTests(unittest.TestCase):
    def setUp(self):
        sample=json.loads((ROOT/'examples/input.json').read_text(encoding='utf-8'))
        self.profile=sample['profile']
        self.role=sample['roles'][0]

    def test_unknown_or_unused_criteria_never_become_full_credit(self):
        self.role['preferred_skills']=[]
        self.role['preferred_hours_per_week']=None
        self.profile['domain_preference_any']=True
        row=match_role(self.profile,self.role)
        self.assertEqual(row['effective_weights'],{'role':1.0})
        self.assertIsNone(row['component_scores']['skills']['score'])
        self.assertIsNone(row['component_scores']['domain']['score'])
        self.profile['field_status']['intended_roles']='unknown'
        row=match_role(self.profile,self.role)
        self.assertIsNone(row['match'])
        self.assertEqual(row['scoring_status'],'insufficient_data')

    def test_real_zero_is_valid_and_distinct_from_null(self):
        self.role.update(required_skills=[],preferred_skills=[],min_hours_per_week=None,
                         preferred_hours_per_week=None,project_domains=[])
        self.profile.update(primary_role=None,intended_roles=[])
        row=match_role(self.profile,self.role)
        self.assertEqual(row['match'],0)
        self.assertEqual(row['scoring_status'],'complete')

    def test_inconsistent_or_nonreciprocal_ahp_rejected(self):
        inconsistent=[[1,9,1/9,9],[1/9,1,9,1/9],[9,1/9,1,9],[1/9,9,1/9,1]]
        with self.assertRaisesRegex(ValueError,'consistency'):
            calculate_weights(inconsistent)
        nonreciprocal=[[1,2,3,4],[1,1,2,3],[1/3,1/2,1,2],[1/4,1/3,1/2,1]]
        with self.assertRaisesRegex(ValueError,'reciprocal'):
            calculate_weights(nonreciprocal)

    def test_weight_normalization_and_formula_reproduce_total(self):
        row=match_role(self.profile,self.role)
        self.assertAlmostEqual(sum(row['effective_weights'].values()),1)
        total=sum(row['effective_weights'][k]*row['component_scores'][k]['score'] for k in row['effective_weights'])
        self.assertEqual(int(total+.5),row['match'])
        self.assertAlmostEqual(calculate_weights()['CR'],0.011475369739962236)
