import { List } from 'antd';
import { Link } from 'react-router-dom';
import type { AgentModel } from '@/types/domain/model';

interface ModelListProps {
  models: AgentModel[];
}

export function ModelList({ models }: ModelListProps) {
  return (
    <List
      dataSource={models}
      renderItem={(model) => (
        <List.Item>
          <List.Item.Meta
            title={<Link to={`/models/${model.metadata.name}`}>{model.metadata.title}</Link>}
            description={model.metadata.description}
          />
        </List.Item>
      )}
    />
  );
}
