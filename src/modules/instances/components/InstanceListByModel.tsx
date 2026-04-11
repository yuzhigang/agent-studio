import { Empty, List } from 'antd';
import { Link } from 'react-router-dom';
import type { AgentInstance } from '@/types/domain/instance';

interface InstanceListByModelProps {
  modelId: string;
  instances: AgentInstance[];
}

export function InstanceListByModel({ modelId, instances }: InstanceListByModelProps) {
  if (instances.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No instances yet" />;
  }

  return (
    <List
      dataSource={instances}
      renderItem={(instance) => (
        <List.Item>
          <List.Item.Meta
            title={<Link to={`/models/${modelId}/instances/${instance.id}`}>{instance.metadata.title}</Link>}
            description={instance.metadata.description}
          />
        </List.Item>
      )}
    />
  );
}
