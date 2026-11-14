import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from rolemesh_matching import recommend, recommend_profiles
from rolemesh_matching.integration import run_profiles_request, run_request, load_schema, ContractError
from rolemesh_matching.service import run_matching_service
from rolemesh_matching.normalization import normalize_labels

ROOT = Path(__file__).resolve().parents[1]


class BidirectionalTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/'examples/input.json').read_text(encoding='utf-8'))
        self.profile, self.role = self.data['profile'], self.data['roles'][0]

    def request(self, profiles=None):
        return {'contract_version':'0.1.0','role':self.role,'profiles':[self.profile] if profiles is None else profiles}

    def test_pair_scores_and_reasons_identical_both_directions(self):
        forward = run_request(self.data)['recommendations'][0]
        backward = run_profiles_request(self.request())['recommendations'][0]
        for key in forward:
            if key != 'computed_at':
                self.assertEqual(forward[key], backward[key], key)

    def test_rank_scores_then_skill_role_and_stable_profile_id(self):
        better = copy.deepcopy(self.profile)
        better['profile_id'] = 'profile.better'
        better['skills'][1]['level'] = 4
        other = copy.deepcopy(self.profile)
        other['profile_id'] = 'profile.aaa'
        out = run_profiles_request(self.request([self.profile, better, other]))
        self.assertEqual([r['profile_id'] for r in out['recommendations']], ['profile.better','profile.aaa',self.profile['profile_id']])
        self.assertEqual(out['recommendations'][0]['match'],98)

    def test_failed_unknown_and_provisional_preserved_not_ranked(self):
        values = []
        for name in ('failed','unknown','provisional'):
            p = copy.deepcopy(self.profile)
            p['profile_id'] = name
            values.append(p)
        values[0]['availability_hours_per_week'] = 2
        values[1]['availability_hours_per_week'] = None
        values[2]['skills'][1]['level'] = None
        result = run_profiles_request(self.request(values))
        self.assertEqual(result['recommendations'],[])
        self.assertEqual([r['eligibility'] for r in result['comparisons']],['ineligible','needs_confirmation','eligible'])
        self.assertEqual(result['comparisons'][2]['scoring_status'],'provisional')
        self.assertTrue(all(r['match'] is None for r in result['comparisons']))

    def test_closed_role_never_recommends_profiles(self):
        self.role['recruitment_status'] = 'closed'
        self.assertEqual(run_profiles_request(self.request())['recommendations'],[])

    def test_empty_list_still_validates_role_business_conditions(self):
        self.assertEqual(run_profiles_request(self.request([]))['comparisons'],[])
        self.role['preferred_hours_per_week'] = 1
        with self.assertRaises(ContractError):
            run_profiles_request(self.request([]))

    def test_duplicate_profile_ids_rejected(self):
        with self.assertRaises(ContractError) as error:
            run_profiles_request(self.request([self.profile,self.profile]))
        self.assertEqual(error.exception.code,'BUSINESS_INPUT_INVALID')

    def test_extra_pii_and_wrong_version_rejected_without_echo(self):
        self.profile['phone'] = 'private-candidate-value'
        with self.assertRaises(ContractError) as error:
            run_profiles_request(self.request())
        self.assertNotIn('private-candidate-value',str(error.exception.as_dict()))
        self.profile.pop('phone')
        req = self.request()
        req['contract_version'] = 'next'
        with self.assertRaises(ContractError):
            run_profiles_request(req)

    def test_no_mutation_or_profile_text_disclosure(self):
        before = copy.deepcopy(self.request())
        result = run_profiles_request(self.request())
        self.assertEqual(before,self.request())
        self.assertNotIn('experience_summary',json.dumps(result))
        self.assertNotIn(self.profile['experience_summary'],json.dumps(result,ensure_ascii=False))

    def test_reverse_definitions_match_authoritative_dto(self):
        self.assertEqual(load_schema('profiles-input')['$defs'],load_schema('input')['$defs'])
        self.assertEqual(load_schema('profiles-output')['$defs'],load_schema('output')['$defs'])
        for name in ('profiles-input','profiles-output','event'):
            Draft202012Validator.check_schema(load_schema(name))
            self.assertEqual(load_schema(name),json.loads((ROOT/f'contracts/{name}.schema.json').read_text(encoding='utf-8')))

    def test_exact_normalization_preserves_unknown_and_negation(self):
        result = normalize_labels(['react.js','想学React','自定义技能'],'skills')
        self.assertEqual(result['codes'],['skill.react'])
        self.assertEqual(result['unknown_labels'],['想学React','自定义技能'])
        self.assertEqual(result['raw'],['react.js','想学React','自定义技能'])
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(normalize_labels([],'skills')['status'],'provided')
        self.assertEqual(normalize_labels(['React','react'],'skills')['codes'],['skill.react'])

    def test_normalizer_rejects_prose_and_unsupported_category(self):
        for labels,category in [('React','skills'),([' '],'skills'),([], 'invented')]:
            with self.assertRaises(ValueError):
                normalize_labels(labels,category)

    def test_seed_vocabulary_packaged_identically(self):
        self.assertEqual((ROOT/'contracts/codebook_seed.json').read_bytes(),(ROOT/'rolemesh_matching/data/codebook_seed.json').read_bytes())

    def test_optional_model_fallback_is_explicit_not_fake_score(self):
        self.role['project_domains'] = []
        self.role['raw_fields'] = {'project_domains':'教育科技'}
        class Broken:
            def similarity(self, a, b):
                raise RuntimeError('secret provider detail')
        for request,direction in [(self.request(),'profiles'),({'contract_version':'0.1.0','profile':self.profile,'roles':[self.role]},'projects')]:
            result = run_matching_service(request,direction=direction,semantic=Broken())
            row = result['comparisons'][0]
            self.assertIsNone(row['match'])
            self.assertIn('semantic_unavailable_fallback',row['warnings'])
            self.assertNotIn('secret provider detail',json.dumps(result))
            self.assertIsNone(row['model_id'])

    def test_successful_model_not_marked_degraded(self):
        self.role['project_domains'] = []
        self.role['raw_fields'] = {'project_domains':'教育科技'}
        class Stub:
            model_id,revision = 'test-stub','test'
            def similarity(self,a,b):
                return 0.6
        row = run_matching_service(self.request(),direction='profiles',semantic=Stub())['recommendations'][0]
        self.assertEqual(row['component_scores']['domain']['score'],50)
        self.assertNotIn('semantic_unavailable_fallback',row['warnings'])

    def test_invalid_model_output_fallback_and_invalid_request_propagates(self):
        self.role['project_domains'] = []
        self.role['raw_fields'] = {'project_domains':'教育科技'}
        class Invalid:
            def similarity(self,a,b):
                return float('nan')
        row = run_matching_service(self.request(),direction='profiles',semantic=Invalid())['comparisons'][0]
        self.assertIn('semantic_unavailable_fallback',row['warnings'])
        with self.assertRaises(ContractError):
            run_matching_service({'profile':'invalid'},semantic=Invalid())
        with self.assertRaises(ValueError):
            run_matching_service({},direction='other')

    def test_service_without_ai_equals_direct_core(self):
        a = run_request(self.data)
        b = run_matching_service(self.data)
        self.assertEqual([r['match'] for r in a['comparisons']],[r['match'] for r in b['comparisons']])
