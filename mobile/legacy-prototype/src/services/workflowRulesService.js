// CivicLens - Configurable Workflow Orchestration Service (custom backend)
import { apiRequest, isBackendConfigured } from './apiClient';

export async function loadWorkflowRules() {
  if (!isBackendConfigured) return [];
  const { data, error } = await apiRequest('/workflow-rules');
  if (error) {
    console.log('loadWorkflowRules error:', error);
    return [];
  }
  return data?.rules || [];
}

export async function createWorkflowRule(userId, rule) {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { data, error } = await apiRequest('/workflow-rules', {
    method: 'POST',
    body: {
      ruleName: rule.ruleName,
      matchCategory: rule.matchCategory || null,
      matchKeywords: rule.matchKeywords || [],
      routeToDepartmentId: rule.routeToDepartmentId,
      notifyRole: rule.notifyRole || 'official',
      priority: rule.priority ?? 100,
    },
  });
  if (error) return { success: false, error };
  return { success: true, rule: data.rule };
}

export async function toggleWorkflowRule(ruleId, active) {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { error } = await apiRequest(`/workflow-rules/${ruleId}/toggle`, { method: 'PATCH', body: { active } });
  return { success: !error, error };
}

export async function deleteWorkflowRule(ruleId) {
  if (!isBackendConfigured) return { success: false, error: 'Backend not configured.' };
  const { error } = await apiRequest(`/workflow-rules/${ruleId}`, { method: 'DELETE' });
  return { success: !error, error };
}

/**
 * Same routing-decision logic as before — purely client-side, no
 * backend dependency (given the rules array already loaded).
 */
export function resolveRouteFromRules(rules, category, text) {
  const lowerText = (text || '').toLowerCase();
  const activeSorted = rules.filter((r) => r.active).sort((a, b) => a.priority - b.priority);

  for (const rule of activeSorted) {
    const categoryMatches = !rule.match_category || rule.match_category === category;
    const keywordMatches =
      !rule.match_keywords ||
      rule.match_keywords.length === 0 ||
      rule.match_keywords.some((kw) => lowerText.includes(kw.toLowerCase()));

    if (categoryMatches && keywordMatches) {
      return { ruleId: rule.id, ruleName: rule.rule_name, departmentId: rule.route_to_department_id, notifyRole: rule.notify_role };
    }
  }
  return null;
}
