import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { XCircle, AlertCircle, Info } from 'lucide-react';

interface Alert {
  id: string;
  type: 'error' | 'warning' | 'info';
  message: string;
  timestamp: string;
}

const alerts: Alert[] = [
  { id: '1', type: 'warning', message: 'Email Assistant failure rate increased to 8%', timestamp: '10 minutes ago' },
  { id: '2', type: 'info', message: 'Customer Support Agent usage spike detected', timestamp: '25 minutes ago' },
  { id: '3', type: 'error', message: 'Data Processing flow failed 3 times in a row', timestamp: '1 hour ago' },
  { id: '4', type: 'warning', message: 'API quota at 85% for OpenAI', timestamp: '2 hours ago' },
  { id: '5', type: 'info', message: 'New agent "Marketing Assistant" deployed', timestamp: '3 hours ago' },
];

export function SystemAlertsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>System Alerts</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors"
            >
              {alert.type === 'error' && <XCircle className="w-4 h-4 text-red-600 shrink-0" />}
              {alert.type === 'warning' && <AlertCircle className="w-4 h-4 text-yellow-600 shrink-0" />}
              {alert.type === 'info' && <Info className="w-4 h-4 text-blue-600 shrink-0" />}
              <div className="flex-1">
                <div className="font-medium">{alert.message}</div>
                <div className="text-sm text-muted-foreground">{alert.timestamp}</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

