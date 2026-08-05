import { useState, useEffect } from 'react';
import { ArrowRight, ChevronRight, Sparkles } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { useNavigate } from 'react-router-dom';
import {
  ActiveAgentsTab,
  ActiveFlowsTab,
  RecentExecutionsTab,
  GaugeRow,
  MetricGauge,
} from '../components/dashboard';
import { getAgentRunsCountLast7Days, getAgentRunsForMetrics, getRecentAgentRuns, getDashboardActiveFlows, type AgentRunMetricsDoc, type DashboardFlowItem } from '../services/dashboardApi';
import type { AgentRunDoc } from '../services/agentRunApi';
import { getAgents } from '../services/agentApi';
import { getProviders } from '../services/providerApi';
import type { AgentDoc, AIProvider } from '../types/agent.types';
import { settleAll } from '../lib/settleAll';

interface DashboardMetrics {
  totalRuns: number;
  successRate: number;
  avgRuntime: number;
  totalCost: number;
}

/**
 * Calculate success rate from agent runs
 */
function calculateSuccessRate(runs: AgentRunMetricsDoc[]): number {
  if (runs.length === 0) return 0;
  const successCount = runs.filter(
    (run) => run.status === 'Success' || run.status === 'success'
  ).length;
  return (successCount / runs.length) * 100;
}

/**
 * Calculate average runtime from agent runs
 */
function calculateAvgRuntime(runs: AgentRunMetricsDoc[]): number {
  const validRuns = runs.filter(
    (run) => run.start_time && run.end_time
  );

  if (validRuns.length === 0) return 0;

  const totalMs = validRuns.reduce((sum, run) => {
    try {
      const start = new Date(run.start_time!);
      const end = new Date(run.end_time!);
      
      if (isNaN(start.getTime()) || isNaN(end.getTime())) {
        return sum;
      }

      const diff = end.getTime() - start.getTime();
      return diff >= 0 ? sum + diff : sum;
    } catch {
      return sum;
    }
  }, 0);

  return totalMs / validRuns.length;
}

/**
 * Calculate total cost from agent runs
 */
function calculateTotalCost(runs: AgentRunMetricsDoc[]): number {
  return runs.reduce((sum, run) => {
    const cost = run.cost;
    return sum + (typeof cost === 'number' && !isNaN(cost) ? cost : 0);
  }, 0);
}

/**
 * Format duration in milliseconds to human-readable string
 */
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/**
 * Format number with commas
 */
function formatNumber(num: number): string {
  return num.toLocaleString('en-US');
}

/**
 * Format currency with up to 4 decimal places
 * Shows more decimal places for very small values
 */
function formatCurrency(amount: number): string {
  // Format with up to 4 decimal places, removing trailing zeros
  const formatted = amount.toFixed(4);
  // Remove trailing zeros but keep at least 2 decimal places
  const trimmed = formatted.replace(/\.?0+$/, '');
  
  // If no decimal point, add .00
  if (!trimmed.includes('.')) {
    return `$${trimmed}.00`;
  }
  
  // Ensure at least 2 decimal places for consistency
  const parts = trimmed.split('.');
  const decimals = parts[1];
  if (decimals.length < 2) {
    return `$${parts[0]}.${decimals.padEnd(2, '0')}`;
  }
  
  return `$${trimmed}`;
}

export { HomePage };
export default HomePage;

function HomePage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('agents');
  const [metrics, setMetrics] = useState<DashboardMetrics>({
    totalRuns: 0,
    successRate: 0,
    avgRuntime: 0,
    totalCost: 0,
  });
  const [metricsLoading, setMetricsLoading] = useState(true);
  
  // Data for tabs - loaded once on mount
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentRuns, setAgentRuns] = useState<AgentRunDoc[]>([]);
  const [agentRunsLoading, setAgentRunsLoading] = useState(true);
  const [flows, setFlows] = useState<DashboardFlowItem[]>([]);
  const [flowsLoading, setFlowsLoading] = useState(true);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);

  useEffect(() => {
    async function fetchAllData() {
      try {
        // Fetch all data in parallel - one denied widget must not blank the
        // rest of the dashboard, so each slot is isolated via settleAll.
        const widgetLabels = ['run count', 'run metrics', 'agents', 'recent runs', 'flows', 'providers'];
        const [totalRuns, runsData, agentsData, recentRuns, flowsData, providersData] = await settleAll(
          [
            getAgentRunsCountLast7Days(),
            getAgentRunsForMetrics(),
            getAgents({
              status: 'active',
              limit: 10,
              page: 1,
            }),
            getRecentAgentRuns(),
            getDashboardActiveFlows(10),
            getProviders(),
          ],
          (index, error) => {
            console.error(`Error fetching dashboard ${widgetLabels[index]}:`, error);
          },
        );

        // Process metrics
        if (runsData) {
          setMetrics({
            totalRuns: totalRuns ?? 0,
            successRate: calculateSuccessRate(runsData),
            avgRuntime: calculateAvgRuntime(runsData),
            totalCost: calculateTotalCost(runsData),
          });
        }

        // Process agents
        if (agentsData) {
          const agentList = Array.isArray(agentsData) ? agentsData : agentsData.items;
          const activeAgents = agentList.filter((agent) => agent.disabled === 0);
          setAgents(activeAgents.slice(0, 10));
        }

        // Set agent runs
        if (recentRuns) setAgentRuns(recentRuns);

        // Set flows
        if (flowsData) setFlows(flowsData);

        // Set providers
        if (providersData) {
          const providerList = Array.isArray(providersData) ? providersData : providersData.items;
          setProviders(providerList);
        }
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
      } finally {
        setMetricsLoading(false);
        setAgentsLoading(false);
        setAgentRunsLoading(false);
        setFlowsLoading(false);
        setProvidersLoading(false);
      }
    }

    fetchAllData();
  }, []);

  const metricsData = [
    {
      id: 'total-runs',
      label: 'Total Agent Runs',
      period: 'Last 7 days',
      value: metricsLoading ? '...' : formatNumber(metrics.totalRuns),
      info: 'Total number of agent executions in the last 7 days',
    },
    {
      id: 'success-rate',
      label: 'Success Rate',
      period: 'Last 7 days',
      value: metricsLoading ? '...' : `${metrics.successRate.toFixed(1)}%`,
      info: 'Percentage of successful agent runs without errors',
    },
    {
      id: 'avg-runtime',
      label: 'Avg Runtime',
      period: 'Last 7 days',
      value: metricsLoading ? '...' : formatDuration(metrics.avgRuntime),
      info: 'Average execution time across all agent runs',
    },
    {
      id: 'cost',
      label: 'Total Cost',
      period: 'Last 7 days',
      value: metricsLoading ? '...' : formatCurrency(metrics.totalCost),
      info: 'Total API costs for LLM usage across all agents',
      flag: true,
    },
  ];

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        {/* HUF Page head */}
        <div>
          <h1 className="font-display font-bold text-[36px] text-ink leading-none tracking-tight">
            Dashboard
          </h1>
          <p className="font-body text-steel text-[14.5px] mt-1">
            Monitor your agents, flows, and system performance
          </p>
        </div>

        {/* HUF Gauge Strip */}
        <GaugeRow>
          {metricsData.map((metric) => (
            <MetricGauge
              key={metric.id}
              label={metric.label}
              period={metric.period}
              value={metric.value}
              info={metric.info}
              flag={metric.flag}
            />
          ))}
        </GaugeRow>

        {/* Empty state card when no AI providers exist */}
        {!providersLoading && providers.length === 0 && (
          <Card className="border-primary/20 bg-primary/5">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-primary">
                  <Sparkles className="h-4 w-4" />
                  <CardTitle className="text-base">Get started with AI</CardTitle>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="font-body text-[13px] font-medium text-steel hover:text-ink hover:bg-transparent pr-1"
                  onClick={() => navigate('/providers')}
                >
                  View all providers
                  <ChevronRight className="w-[11px] h-[11px] ml-0.5" strokeWidth={2} />
                </Button>
              </div>
              <CardDescription>
                No AI providers connected yet. Connect a provider to start creating and running agents. Pick a quick-start path or add custom provider credentials.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row">
              <Button
                variant="outline"
                className="h-auto flex-1 justify-between whitespace-normal text-left p-4"
                onClick={() => navigate('/providers?starter=openrouter')}
              >
                <div>
                  <span className="block font-medium">Try OpenRouter Free</span>
                  <span className="mt-1 block text-xs text-muted-foreground">openrouter/free · Zero-cost router for free models</span>
                </div>
                <ArrowRight className="ml-3 h-4 w-4 shrink-0" />
              </Button>
              <Button
                variant="outline"
                className="h-auto flex-1 justify-between whitespace-normal text-left p-4"
                onClick={() => navigate('/providers?starter=google')}
              >
                <div>
                  <span className="block font-medium">Try Gemini with Google AI Studio</span>
                  <span className="mt-1 block text-xs text-muted-foreground">gemini-3.5-flash · Fast and intelligent model</span>
                </div>
                <ArrowRight className="ml-3 h-4 w-4 shrink-0" />
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Tabbed Interface */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-0">
          <div className="flex items-center justify-between border-b border-ink mb-2">
            <TabsList className="border-b-0">
              <TabsTrigger value="agents">Agents</TabsTrigger>
              <TabsTrigger value="flows">Flows</TabsTrigger>
              <TabsTrigger value="executions">Executions</TabsTrigger>
            </TabsList>
            <Button
              variant="ghost"
              size="sm"
              className="font-body text-[13px] font-medium text-steel hover:text-ink hover:bg-transparent pr-1"
              onClick={() => {
                if (activeTab === 'agents') navigate('/agents');
                else if (activeTab === 'flows') navigate('/flows');
                else if (activeTab === 'executions') navigate('/executions');
              }}
            >
              Show more
              <ChevronRight className="w-[11px] h-[11px] ml-0.5" strokeWidth={2} />
            </Button>
          </div>

          {/* Agents Tab */}
          <TabsContent value="agents" className="space-y-4">
            <ActiveAgentsTab agents={agents} loading={agentsLoading} />
          </TabsContent>

          {/* Flows Tab */}
          <TabsContent value="flows" className="space-y-4">
            <ActiveFlowsTab flows={flows} loading={flowsLoading} />
          </TabsContent>

          {/* Executions Tab */}
          <TabsContent value="executions" className="space-y-4">
            <RecentExecutionsTab runs={agentRuns} loading={agentRunsLoading} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
