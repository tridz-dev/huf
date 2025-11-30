import { useState } from 'react';
import { Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/tooltip';
import { Button } from '../components/ui/button';
import { useNavigate } from 'react-router-dom';
import { ActiveAgentsTab, ActiveFlowsTab, RecentExecutionsTab } from '../components/dashboard';

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
            <RecentExecutionsTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
