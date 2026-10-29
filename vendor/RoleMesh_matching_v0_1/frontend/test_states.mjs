import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {toFrontendStates} from './bridge.mjs';
const cases=JSON.parse(readFileSync(new URL('../examples/contract_results.json',import.meta.url),'utf8'));
const expected={normal:'ready',unknown_required_level:'needs_confirmation',unknown_time:'needs_confirmation',
 missing_required_skill:'not_eligible',insufficient_time:'not_eligible',zero_time:'not_eligible',
 no_domain_preference:'ready',no_preferred_skills:'ready',unknown_soft_level:'incomplete_scoring',
 closed_role:'not_recruiting',time_wrong_type:'request_error',wrong_contract_version:'request_error',updated_profile_version:'ready'};
for(const {id,response} of cases) {
 const states=toFrontendStates(response);
 assert.equal(states[0].state,expected[id],id);
 if(!['ready','request_error'].includes(states[0].state)) assert.equal(states[0].match,null,id);
}
console.log(`Frontend states: ${cases.length} shared fixtures passed`);
