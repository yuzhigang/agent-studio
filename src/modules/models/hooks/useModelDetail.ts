import { message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { modelService } from '@/mocks/services/modelService';
import { buildModelJsonBlocks } from '@/modules/models/adapters/modelAdapters';
import { parseJsonBlock, prettyJson } from '@/shared/lib/json';
import { validateModelDraft } from '@/shared/lib/validators/model';
import type { AgentModel } from '@/types/domain/model';

function buildJsonDrafts(model: AgentModel | null): Record<string, string> {
  if (!model) {
    return {};
  }

  return Object.fromEntries(buildModelJsonBlocks(model).map((block) => [block.key, prettyJson(block.value)]));
}

export function useModelDetail(modelId: string) {
  const [loading, setLoading] = useState(true);
  const [original, setOriginal] = useState<AgentModel | null>(null);
  const [draft, setDraft] = useState<AgentModel | null>(null);
  const [saving, setSaving] = useState(false);
  const [jsonErrors, setJsonErrors] = useState<Record<string, string | null>>({});
  const [jsonDrafts, setJsonDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    setLoading(true);

    modelService.getByName(modelId).then((model) => {
      if (!active) {
        return;
      }

      const nextOriginal = model ? structuredClone(model) : null;
      const nextDraft = model ? structuredClone(model) : null;
      setOriginal(nextOriginal);
      setDraft(nextDraft);
      setJsonErrors({});
      setJsonDrafts(buildJsonDrafts(nextDraft));
      setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [modelId]);

  const dirty = useMemo(() => JSON.stringify(original) !== JSON.stringify(draft), [original, draft]);

  async function save() {
    if (!draft) {
      return;
    }

    if (Object.values(jsonErrors).some(Boolean)) {
      message.error('Fix JSON errors before saving.');
      return;
    }

    const errors = validateModelDraft(draft);
    if (errors.length > 0) {
      message.error(errors[0]);
      return;
    }

    setSaving(true);
    try {
      await modelService.update(draft);
      const next = structuredClone(draft);
      setOriginal(next);
      setDraft(next);
      setJsonDrafts(buildJsonDrafts(next));
      setJsonErrors({});
      message.success('Saved');
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Failed to save model';
      message.error(reason);
    } finally {
      setSaving(false);
    }
  }

  function reset() {
    const nextDraft = original ? structuredClone(original) : null;
    setDraft(nextDraft);
    setJsonDrafts(buildJsonDrafts(nextDraft));
    setJsonErrors({});
  }

  function setMetadata<K extends keyof AgentModel['metadata']>(key: K, value: AgentModel['metadata'][K]) {
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

  function setDefinitions(
    section: 'attributes' | 'variables',
    value: AgentModel['attributes'] | AgentModel['variables'],
  ) {
    setDraft((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        [section]: value,
      };
    });
  }

  function updateJsonBlock(key: keyof AgentModel, raw: string) {
    setJsonDrafts((current) => ({ ...current, [key]: raw }));

    try {
      const parsed = parseJsonBlock<unknown>(raw);
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
    setMetadata,
    setDefinitions,
    updateJsonBlock,
  };
}
