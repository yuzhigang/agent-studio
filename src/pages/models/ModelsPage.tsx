import { useParams } from 'react-router-dom';
import { ConfigWorkbench } from '@/modules/workbench/components/ConfigWorkbench';

export function ModelsPage() {
  const { modelId = '', instanceId = '' } = useParams();

  return <ConfigWorkbench modelIdParam={modelId} instanceIdParam={instanceId} />;
}
