import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {toFrontendProjects} from './bridge.mjs';
const response = JSON.parse(readFileSync(new URL('../examples/output.json', import.meta.url), 'utf8'));
const input = JSON.parse(readFileSync(new URL('../examples/input.json', import.meta.url), 'utf8'));
const metadata = new Map();
for (const r of input.roles) {
  if (!metadata.has(r.project_id)) metadata.set(r.project_id, {name:r.project_id, roles:[]});
  metadata.get(r.project_id).roles.push({role_id:r.role_id, name:r.name});
}
const out = toFrontendProjects(response, metadata);
assert.equal(out.length, response.projects.length);
assert.ok(out.every(p => p.matchRoles.every(r => r.reasons.every(x => typeof x === 'string'))));
assert.deepEqual(toFrontendProjects({contract_version:'0.1.0',projects:[],recommendations:[]}, metadata), []);
assert.throws(() => toFrontendProjects(response, new Map()), /metadata/);
const zero = structuredClone(response);
for (const r of zero.recommendations) r.match = 0;
for (const p of zero.projects) p.match = 0;
assert.ok(toFrontendProjects(zero, metadata).every(p => p.match === 0));
const invalid = structuredClone(response);
invalid.recommendations[0].match = null;
assert.throws(() => toFrontendProjects(invalid, metadata));
console.log('Frontend adapter: 6 checks passed');
