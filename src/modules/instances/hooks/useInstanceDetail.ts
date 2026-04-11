import { message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { instanceService } from '@/mocks/services/instanceService';
import { buildRuntimeJsonBlocks } from '@/modules/instances/adapters/instanceAdapters';
import { parseJsonBlock, prettyJson } from '@/shared/lib/json';
import { validateInstanceDraft } from '@/shared/lib/validators/instance';
import type { AgentBinding, AgentInstance } from '@/types/domain/instance';

function buildRuntimeJsonDrafts(instance: AgentInstance | null): Record<string, string> {
  if (!instance) {
    return {};
  }

  return Object.fromEntries(buildRuntimeJsonBlocks(instance).map((block) => [block.key, prettyJson(block.value)]));
}

export function useInstanceDetail(modelId: string, instanceId: string) {
  const [loading, setLoading] = useState(true);
  const [original, setOriginal] = useState<AgentInstance | null>(null);
  const [draft, setDraft] = useState<AgentInstance | null>(null);
  const [saving, setSaving] = useState(false);
  const [jsonErrors, setJsonErrors] = useState<Record<string, string | null>>({});
  const [jsonDrafts, setJsonDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    setLoading(true);

    instanceService.getById(instanceId).then((instance) => {
      if (!active) {
        return;
      }

      const scopedInstance = instance && instance.modelId === modelId ? instance : null;
      const nextOriginal = scopedInstance ? structuredClone(scopedInstance) : null;
      const nextDraft = scopedInstance ? structuredClone(scopedInstance) : null;
      setOriginal(nextOriginal);
      setDraft(nextDraft);
      setJsonErrors({});
      setJsonDrafts(buildRuntimeJsonDrafts(nextDraft));
      setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [instanceId, modelId]);

  const dirty = useMemo(() => JSON.stringify(original) !== JSON.stringify(draft), [original, draft]);

  async function save() {
    if (!draft) {
      return;
    }

    if (draft.modelId !== modelId) {
      message.error('Instance does not belong to this model');
      return;
    }

    if (Object.values(jsonErrors).some(Boolean)) {
      message.error('Fix JSON errors before saving.');
      return;
    }

    const errors = validateInstanceDraft(draft);
    if (errors.length > 0) {
      message.error(errors[0]);
      return;
    }

    setSaving(true);
    try {
      await instanceService.update(draft);
      const next = structuredClone(draft);
      setOriginal(next);
      setDraft(next);
      setJsonErrors({});
      setJsonDrafts(buildRuntimeJsonDrafts(next));
      message.success('Saved');
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Failed to save instance';
      message.error(reason);
    } finally {
      setSaving(false);
    }
  }

  function reset() {
    const nextDraft = original ? structuredClone(original) : null;
    setDraft(nextDraft);
    setJsonErrors({});
    setJsonDrafts(buildRuntimeJsonDrafts(nextDraft));
  }

  function updateMetadata<K extends keyof AgentInstance['metadata']>(key: K, value: AgentInstance['metadata'][K]) {
    setDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        metadata: {
          ...current.metadata,
          [key]: value,
        },
      };
    });
  }

  function updateField(section: 'attributes' | 'variables', key: string, value: unknown) {
    setDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        [section]: {
          ...(current[section] ?? {}),
          [key]: value,
        },
      };
    });
  }

  function updateBindings(value: Record<string, AgentBinding>) {
    setDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        bindings: value,
      };
    });
  }

  function updateRuntimeBlock(key: 'memory' | 'activeGoals' | 'currentPlan' | 'extensions', raw: string) {
    setJsonDrafts((current) => ({ ...current, [key]: raw }));

    try {
      const parsed = parseJsonBlock(raw);
      setJsonErrors((current) => ({ ...current, [key]: null }));
      setDraft((current) => (current ? { ...current, [key]: parsed } : current));
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Invalid JSON';
      setJsonErrors((current) => ({ ...current, [key]: reason }));
    }
  }

  return {
    loading,
    draft,
    dirty,
    saving,
    jsonErrors,
    jsonDrafts,
    save,
    reset,
    updateMetadata,
    updateField,
    updateBindings,
    updateRuntimeBlock,
  };
}
