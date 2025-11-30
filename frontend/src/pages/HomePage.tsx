import { useState } from 'react';
import { Info, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/tooltip';
import { Button } from '../components/ui/button';
import { useNavigate } from 'react-router-dom';
import { ActiveAgentsTab, ActiveFlowsTab } from '../components/dashboard';

const metrics = [
  {
    id: 'total-runs',
    title: 'Total Agent Runs',
    subtitle: 'Last 7 days',
    value: '1,247',
    tooltip: 'Total number of agent executions in the last 7 days',
  },
  {
    id: 'success-rate',
    title: 'Success Rate',
    subtitle: 'Last 7 days',
    value: '94.2%',
    tooltip: 'Percentage of successful agent runs without errors',
  },
  {
    id: 'avg-runtime',
    title: 'Avg Runtime',
    subtitle: 'Last 7 days',
    value: '2.3s',
    tooltip: 'Average execution time across all agent runs',
  },
  {
    id: 'cost',
    title: 'Total Cost',
    subtitle: 'Last 7 days',
    value: '$23.45',
    tooltip: 'Total API costs for LLM usage across all agents',
  },
];


const recentExecutions = [
  { id: '1', agent: 'Customer Support Agent', status: 'success', duration: '1.8s', timestamp: '2 minutes ago' },
  { id: '2', agent: 'Data Analyst Agent', status: 'success', duration: '3.2s', timestamp: '4 minutes ago' },
  { id: '3', agent: 'Email Assistant', status: 'failed', duration: '0.5s', timestamp: '6 minutes ago' },
  { id: '4', agent: 'Sales Bot', status: 'success', duration: '2.1s', timestamp: '8 minutes ago' },
  { id: '5', agent: 'Content Generator', status: 'success', duration: '4.5s', timestamp: '11 minutes ago' },
  { id: '6', agent: 'Customer Support Agent', status: 'success', duration: '1.9s', timestamp: '15 minutes ago' },
  { id: '7', agent: 'Data Analyst Agent', status: 'success', duration: '2.8s', timestamp: '18 minutes ago' },
];

const alerts = [
  { id: '1', type: 'warning', message: 'Email Assistant failure rate increased to 8%', timestamp: '10 minutes ago' },
  { id: '2', type: 'info', message: 'Customer Support Agent usage spike detected', timestamp: '25 minutes ago' },
  { id: '3', type: 'error', message: 'Data Processing flow failed 3 times in a row', timestamp: '1 hour ago' },
  { id: '4', type: 'warning', message: 'API quota at 85% for OpenAI', timestamp: '2 hours ago' },
  { id: '5', type: 'info', message: 'New agent "Marketing Assistant" deployed', timestamp: '3 hours ago' },
];

export function HomePage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('agents');

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Monitor your agents, flows, and system performance
          </p>
        </div>

        {/* Metrics Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <TooltipProvider>
            {metrics.map((metric) => (
              <Card key={metric.id}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    {metric.title}
                  </CardTitle>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-4 w-4 text-muted-foreground cursor-help" />
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="max-w-xs">{metric.tooltip}</p>
                    </TooltipContent>
                  </Tooltip>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-muted-foreground mb-2">
                    {metric.subtitle}
                  </div>
                  <div className="text-2xl font-bold">{metric.value}</div>
                </CardContent>
              </Card>
            ))}
          </TooltipProvider>
        </div>

        {/* Tabbed Interface */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <div className="flex items-center justify-between">
            <TabsList>
              <TabsTrigger value="agents">Agents</TabsTrigger>
              <TabsTrigger value="flows">Flows</TabsTrigger>
              <TabsTrigger value="executions">Executions</TabsTrigger>
              <TabsTrigger value="alerts">Alerts</TabsTrigger>
            </TabsList>
            {activeTab === 'agents' && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate('/agents')}
              >
                Show More
              </Button>
            )}
          </div>

          {/* Agents Tab */}
          <TabsContent value="agents" className="space-y-4">
            <ActiveAgentsTab />
          </TabsContent>

          {/* Flows Tab */}
          <TabsContent value="flows" className="space-y-4">
            <ActiveFlowsTab />
          </TabsContent>

          {/* Executions Tab */}
          <TabsContent value="executions" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Recent Executions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {recentExecutions.map((execution) => (
                    <div
                      key={execution.id}
                      className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center gap-3 flex-1">
                        {execution.status === 'success' ? (
                          <CheckCircle className="w-4 h-4 text-green-600" />
                        ) : (
                          <XCircle className="w-4 h-4 text-red-600" />
                        )}
                        <div className="flex-1">
                          <div className="font-medium">{execution.agent}</div>
                          <div className="text-sm text-muted-foreground">
                            {execution.duration} • {execution.timestamp}
                          </div>
                        </div>
                      </div>
                      <Badge variant={execution.status === 'success' ? 'default' : 'destructive'}>
                        {execution.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Alerts Tab */}
          <TabsContent value="alerts" className="space-y-4">
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
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
