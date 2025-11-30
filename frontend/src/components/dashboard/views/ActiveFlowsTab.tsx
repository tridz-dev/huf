import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Sparkles } from 'lucide-react';

interface Flow {
  id: string;
  name: string;
  status: 'active';
  runs: number;
  last_run: string;
}

const activeFlows: Flow[] = [
  { id: '1', name: 'Webform Handler', status: 'active', runs: 523, last_run: '2 minutes ago' },
  { id: '2', name: 'Email Automation', status: 'active', runs: 389, last_run: '5 minutes ago' },
  { id: '3', name: 'Slack Notification', status: 'active', runs: 234, last_run: '12 minutes ago' },
  { id: '4', name: 'Data Processing', status: 'active', runs: 156, last_run: '1 hour ago' },
  { id: '5', name: 'Customer Onboarding', status: 'active', runs: 98, last_run: '3 hours ago' },
];

export function ActiveFlowsTab() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle>Active Flows</CardTitle>
        <Badge variant="secondary" className="flex items-center gap-1.5">
          <Sparkles className="w-3 h-3" />
          Coming Soon
        </Badge>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {activeFlows.map((flow) => (
            <div
              key={flow.id}
              className="flex items-center justify-between p-3 rounded-lg border opacity-60"
            >
              <div className="flex-1">
                <div className="font-medium">{flow.name}</div>
                <div className="text-sm text-muted-foreground">
                  {flow.runs} runs • Last run {flow.last_run}
                </div>
              </div>
              <Badge variant="default">Active</Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

