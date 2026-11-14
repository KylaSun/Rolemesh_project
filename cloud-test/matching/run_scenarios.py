"""Repeatable synthetic acceptance cases; records expected and actual results."""
import argparse
import copy
import json
from pathlib import Path
from rolemesh_matching.integration import run_request, run_profiles_request, ContractError

ROOT=Path(__file__).resolve().parent


def cases():
    base=json.loads((ROOT/'examples/input.json').read_text(encoding='utf-8'))
    base['roles']=base['roles'][:1]
    result=[]
    def add(name,change,expected):
        data=copy.deepcopy(base)
        change(data)
        result.append({'id':name,'direction':'projects','input':data,'expected':expected})
    add('normal',lambda d:None,{'eligibility':'eligible','match':74})
    add('required_missing',lambda d:d['profile'].update(skills=[]),{'eligibility':'ineligible','match':None})
    add('required_low_level',lambda d:d['profile']['skills'][0].update(level=2),{'eligibility':'ineligible','match':None})
    add('required_unknown_level',lambda d:d['profile']['skills'][0].update(level=None),{'eligibility':'needs_confirmation','match':None})
    add('time_insufficient',lambda d:d['profile'].update(availability_hours_per_week=2),{'eligibility':'ineligible','match':None})
    add('time_at_minimum',lambda d:d['profile'].update(availability_hours_per_week=4),{'eligibility':'eligible','match':72})
    add('time_unknown',lambda d:d['profile'].update(availability_hours_per_week=None),{'eligibility':'needs_confirmation','match':None})
    add('time_zero',lambda d:d['profile'].update(availability_hours_per_week=0),{'eligibility':'ineligible','match':None})
    add('time_wrong_type',lambda d:d['profile'].update(availability_hours_per_week='6'),{'error_code':'INPUT_INVALID'})
    add('missing_profile_version',lambda d:d['profile'].pop('profile_version'),{'error_code':'INPUT_INVALID'})
    add('unconfirmed_codes',lambda d:d['profile']['field_status'].update(skills='unknown'),{'eligibility':'needs_confirmation','match':None})
    add('unknown_soft_preference',lambda d:d['profile']['field_status'].update(domain_interests='unknown'),{'eligibility':'eligible','scoring_status':'provisional','match':None})
    add('domain_any',lambda d:d['profile'].update(domain_preference_any=True),{'eligibility':'eligible','match':69})
    add('paused_role',lambda d:d['roles'][0].update(recruitment_status='paused'),{'eligibility':'ineligible','match':None})
    add('no_openings',lambda d:d['roles'][0].update(openings_remaining=0),{'eligibility':'ineligible','match':None})
    add('language_missing',lambda d:d['profile'].update(languages=[]),{'eligibility':'ineligible','match':None})
    add('year_mismatch',lambda d:d['roles'][0].update(allowed_academic_years=['year.4']),{'eligibility':'ineligible','match':None})
    add('collaboration_mismatch',lambda d:d['roles'][0].update(allowed_collaboration_modes=['in_person']),{'eligibility':'ineligible','match':None})
    add('duplicate_role',lambda d:d['roles'].append(copy.deepcopy(d['roles'][0])),{'error_code':'BUSINESS_INPUT_INVALID'})
    add('model_not_loaded',lambda d:d['roles'][0].update(project_domains=[],raw_fields={'project_domains':'教育科技'}),{'eligibility':'eligible','match':None,'scoring_status':'provisional'})
    for case in result:
        case['input']['profile'].setdefault('raw_fields',{})
    reverse={'contract_version':'0.1.0','role':copy.deepcopy(base['roles'][0]),'profiles':[]}
    for name in ('profile.high','profile.normal','profile.failed','profile.unknown','profile.provisional'):
        p=copy.deepcopy(base['profile'])
        p['profile_id']=name
        if name.endswith('high'):p['skills'][1]['level']=4
        if name.endswith('failed'):p['availability_hours_per_week']=2
        if name.endswith('unknown'):p['availability_hours_per_week']=None
        if name.endswith('provisional'):p['skills'][1]['level']=None
        reverse['profiles'].append(p)
    result.append({'id':'reverse_ranking','direction':'profiles','input':reverse,
        'expected':{'recommended_profile_ids':['profile.high','profile.normal']}})
    empty=copy.deepcopy(reverse);empty['profiles']=[]
    result.append({'id':'reverse_empty','direction':'profiles','input':empty,'expected':{'recommended_profile_ids':[]}})
    return result


def run(output):
    records=[]
    for case in cases():
        try:
            runner=run_request if case['direction']=='projects' else run_profiles_request
            actual=runner(case['input'])
        except ContractError as error:
            actual=error.as_dict()
        expected=case['expected']
        if 'error_code' in expected:
            observed={'error_code':actual.get('error',{}).get('code')}
        elif 'recommended_profile_ids' in expected:
            observed={'recommended_profile_ids':[r['profile_id'] for r in actual['recommendations']]}
        else:
            observed={k:actual['comparisons'][0][k] for k in expected}
        records.append({**case,'actual':actual,'observed':observed,'status':'PASS' if observed==expected else 'FAIL'})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    reverse=next(c for c in records if c['id']=='reverse_ranking')
    (ROOT/'examples/profiles_input.json').write_text(json.dumps(reverse['input'],ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'examples/profiles_output.json').write_text(json.dumps(reverse['actual'],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(records),'passed':sum(c['status']=='PASS' for c in records),'failed':[c['id'] for c in records if c['status']=='FAIL']}))
    return any(c['status']=='FAIL' for c in records)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'examples/acceptance_results.json')
    raise SystemExit(run(parser.parse_args().output))
