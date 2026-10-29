/** Maps backend recommendation output into the existing demo's display shape.
 * No scoring, normalization, authorization, or endpoint assumptions here.
 * metadata: Map<project_id, {name, roles: [{role_id,name}]}> from Kyla's API.
 */
export function toFrontendProjects(response, metadata) {
  if (response?.contract_version !== '0.1.0') throw new Error('Unsupported contract version');
  if (!Array.isArray(response?.recommendations) || !Array.isArray(response?.projects)) {
    throw new TypeError('Expected recommendations and projects arrays');
  }
  return response.projects.map(summary => {
    const meta = metadata.get(summary.project_id);
    if (!meta) throw new Error(`Missing project metadata: ${summary.project_id}`);
    const rows = response.recommendations.filter(r => r.project_id === summary.project_id);
    const matchRoles = rows.map(r => {
      if (r.eligibility !== 'eligible' || r.scoring_status !== 'complete' || !Number.isInteger(r.match) || r.match < 0 || r.match > 100) {
        throw new Error('Only complete formal results can appear in recommendations');
      }
      const role = meta.roles.find(x => x.role_id === r.role_id);
      if (!role) throw new Error(`Missing role metadata: ${r.role_id}`);
      return {role_id: r.role_id, name: role.name, match: r.match,
        reasons: r.reasons.map(x => x.text)};
    });
    const best = rows.find(r => r.role_id === summary.best_role_id);
    if (!best || best.match !== summary.match) throw new Error('Invalid project aggregation');
    return {project_id: summary.project_id, name: meta.name, match: best.match,
      reasons: best.reasons.map(({label, text}) => ({label, text})), matchRoles};
  });
}

export function toFrontendStates(response) {
  if (response?.contract_version !== '0.1.0') throw new Error('Unsupported contract version');
  if (response.error) return [{state:'request_error', label:'数据对接异常', fields:response.error.fields}];
  return response.comparisons.map(r => {
    const base = {role_id:r.role_id, project_id:r.project_id, match:r.match,
      missing_fields:r.missing_fields, unmet_requirements:r.unmet_requirements};
    if (r.eligibility === 'ineligible') {
      const closed = r.hard_checks.some(c => c.code === 'recruitment' && c.status === 'fail');
      return {...base,state:closed?'not_recruiting':'not_eligible',label:closed?'岗位暂不招募':'暂不符合条件'};
    }
    if (r.eligibility === 'needs_confirmation') return {...base,state:'needs_confirmation',label:'请补充必要信息'};
    if (r.scoring_status !== 'complete') return {...base,state:'incomplete_scoring',label:'信息不足，暂不生成正式分数'};
    return {...base,state:'ready',label:'已生成推荐分数'};
  });
}

// Safe minimal renderer. For existing HTML templates, use textContent or proper escaping.
export function renderRecommendations(container, projects) {
  container.replaceChildren();
  for (const p of projects) {
    const card = document.createElement('article');
    const heading = document.createElement('h3');
    heading.textContent = `${p.name} · 匹配分 ${p.match}`;
    card.append(heading);
    for (const reason of p.reasons) {
      const line = document.createElement('p');
      line.textContent = `${reason.label}：${reason.text}`;
      card.append(line);
    }
    container.append(card);
  }
  if (!projects.length) container.textContent = '暂无可正式推荐的项目，请检查待补充信息。';
}
