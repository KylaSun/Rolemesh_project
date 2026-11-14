import copy
import json
from pathlib import Path
import unittest
from rolemesh_matching.integration import run_request, ContractError

ROOT=Path(__file__).resolve().parents[1]


def behavioral(value):
    if isinstance(value,dict):
        return {k:behavioral(v) for k,v in value.items() if k not in ('computed_at','algorithm_version')}
    if isinstance(value,list):
        return [behavioral(v) for v in value]
    return value


class HistoricalRegressionTests(unittest.TestCase):
    def test_full_historical_contract_results_preserved(self):
        cases=json.loads((ROOT/'examples/contract_cases.json').read_text(encoding='utf-8'))
        stored=json.loads((ROOT/'examples/contract_results.json').read_text(encoding='utf-8'))
        old={c['id']:c['response'] for c in stored}
        for case in cases:
            with self.subTest(case=case['id']):
                try:
                    actual=run_request(case['request'])
                except ContractError as error:
                    actual=error.as_dict()
                self.assertEqual(behavioral(actual),behavioral(old[case['id']]))

    def test_experience_self_report_cannot_change_score(self):
        request=json.loads((ROOT/'examples/input.json').read_text(encoding='utf-8'))
        before=run_request(request)
        request['profile'].update(experience_level='expert-claim',experience_summary='自述精通所有技能')
        self.assertEqual(behavioral(before),behavioral(run_request(request)))
