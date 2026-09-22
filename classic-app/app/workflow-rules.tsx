import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { AppButton, Body, Card, Chip, EmptyState, ErrorBanner, Field, H1, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { WorkflowExecution, WorkflowRule } from '../src/api/types.ts';
import { useTheme } from '../src/theme/ThemeContext.tsx';

// Same fixed enums the backend validates against (app.services.ports.WorkflowRuleRecord).
const TRIGGERS = ['complaint.created', 'complaint.status_changed', 'scheduled'];
const ACTIONS = ['notify_admins', 'escalate', 'auto_close', 'assign_least_loaded', 'add_internal_note'];

export default function WorkflowRules() {
  const { colors } = useTheme();
  const [rules, setRules] = useState<WorkflowRule[] | null>(null);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // New-rule form
  const [id, setId] = useState(''); const [name, setName] = useState('');
  const [trigger, setTrigger] = useState(TRIGGERS[0]); const [action, setAction] = useState(ACTIONS[0]);
  const [priority, setPriority] = useState('100');

  const load = useCallback(async () => {
    setError(null);
    try { const r = await endpoints.workflowRules(); setRules(r.rules); setExecutions(r.executions); }
    catch (e: any) { setError(e?.message ?? 'Could not load workflow rules.'); setRules([]); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function toggleActive(r: WorkflowRule) {
    setBusy(r.id); setError(null);
    try { await endpoints.saveWorkflowRule(r.id, { name: r.name, trigger: r.trigger, action: r.action, conditions: r.conditions, params: r.params, priority: r.priority, active: !r.active }); await load(); }
    catch (e: any) { setError(e?.message ?? 'Could not update this rule.'); } finally { setBusy(null); }
  }
  async function remove(r: WorkflowRule) {
    setBusy(r.id); setError(null);
    try { await endpoints.deleteWorkflowRule(r.id); await load(); }
    catch (e: any) { setError(e?.message ?? 'Could not delete this rule.'); } finally { setBusy(null); }
  }
  async function create() {
    setBusy('new'); setError(null);
    try {
      await endpoints.saveWorkflowRule(id.trim().toLowerCase().replace(/\s+/g, '-'), { name, trigger, action, priority: Number(priority) || 100, active: true });
      setId(''); setName(''); await load();
    } catch (e: any) { setError(e?.message ?? 'Could not create this rule.'); } finally { setBusy(null); }
  }

  return (
    <Screen>
      <H1>⚙️ Workflow Rules</H1>
      <Body soft>Configurable rule-based orchestration: when X happens, do Y - the same rules the real complaint pipeline evaluates.</Body>
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}

      {rules === null ? <Loading /> : rules.length === 0 ? <EmptyState message="No workflow rules yet." /> : rules.map((r) => (
        <Card key={r.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ fontWeight: '700', color: colors.text }}>{r.name}</Text>
            <View style={{ backgroundColor: r.active ? colors.ok : colors.textMuted, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
              <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{r.active ? 'active' : 'inactive'}</Text>
            </View>
          </View>
          <Body soft>When {r.trigger.replace(/_/g, ' ')} → {r.action.replace(/_/g, ' ')} · priority {r.priority}</Body>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <AppButton label={r.active ? 'Deactivate' : 'Activate'} kind="secondary" busy={busy === r.id} onPress={() => toggleActive(r)} />
            <AppButton label="Delete" kind="danger" busy={busy === r.id} onPress={() => remove(r)} />
          </View>
        </Card>
      ))}

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>New rule</Text>
      <Card>
        <Field label="Rule ID (unique, e.g. auto-escalate-critical)" value={id} onChangeText={setId} autoCapitalize="none" />
        <Field label="Name" value={name} onChangeText={setName} />
        <Body soft>Trigger</Body>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{TRIGGERS.map((tr) => <Chip key={tr} label={tr.replace(/_/g, ' ')} selected={trigger === tr} onPress={() => setTrigger(tr)} />)}</View>
        <Body soft>Action</Body>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{ACTIONS.map((ac) => <Chip key={ac} label={ac.replace(/_/g, ' ')} selected={action === ac} onPress={() => setAction(ac)} />)}</View>
        <Field label="Priority (lower runs first)" value={priority} onChangeText={setPriority} keyboardType="numeric" />
        <AppButton label="Create rule" busy={busy === 'new'} disabled={!id.trim() || !name.trim()} onPress={create} />
      </Card>

      <Text style={{ fontWeight: '700', color: colors.text, marginTop: 4 }}>Recent executions</Text>
      {executions.length === 0 ? <EmptyState message="No rule has fired yet." /> : executions.slice(0, 20).map((e, i) => (
        <Card key={i}>
          <Body>{e.rule_id} → {e.outcome}</Body>
          <Body soft>Complaint {e.complaint_id.slice(0, 8)} · {new Date(e.executed_at).toLocaleString()}</Body>
        </Card>
      ))}
    </Screen>
  );
}
