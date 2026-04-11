import { Button, Card, Typography, message } from 'antd';
import { instanceService } from '@/mocks/services/instanceService';
import { modelService } from '@/mocks/services/modelService';

export function SettingsPage() {
  async function handleReset() {
    await Promise.all([modelService.reset(), instanceService.reset()]);
    message.success('Local data reset to seed state');
  }

  return (
    <Card>
      <Typography.Title level={2}>Settings</Typography.Title>
      <Typography.Paragraph>
        This page is intentionally small in the MVP and only exposes app info plus local data reset.
      </Typography.Paragraph>
      <Button danger onClick={handleReset}>
        Reset Local Data
      </Button>
    </Card>
  );
}
