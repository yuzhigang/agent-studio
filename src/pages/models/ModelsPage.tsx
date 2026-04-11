import { Card, Flex, Spin, Typography } from 'antd';
import { CreateModelModal } from '@/modules/models/components/CreateModelModal';
import { ModelList } from '@/modules/models/components/ModelList';
import { useModelsPage } from '@/modules/models/hooks/useModelsPage';

export function ModelsPage() {
  const { models, loading, createModel } = useModelsPage();

  return (
    <Card>
      <Flex justify="space-between" align="center" style={{ marginBottom: 16 }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          Models
        </Typography.Title>
        <CreateModelModal existingNames={models.map((model) => model.metadata.name)} onCreate={createModel} />
      </Flex>
      {loading ? <Spin /> : <ModelList models={models} />}
    </Card>
  );
}
