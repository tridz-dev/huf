import { useState, useEffect } from 'react';
import { Info, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/tooltip';
import { Button } from '../components/ui/button';
import { useNavigate } from 'react-router-dom';
import { ActiveAgentsTab, ActiveFlowsTab, RecentExecutionsTab } from '../components/dashboard';
import { getAgentRunsCountLast7Days, getAgentRunsForMetrics, getRecentAgentRuns, type AgentRunMetricsDoc } from '../services/dashboardApi';
import type { AgentRunDoc } from '../services/agentRunApi';
import { getAgents } from '../services/agentApi';
import type { AgentDoc } from '../types/agent.types';

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

  useEffect(() => {
    async function fetchAllData() {
      try {
        // Fetch all data in parallel
        const [totalRuns, runsData, agentsData, recentRuns] = await Promise.all([
          getAgentRunsCountLast7Days(),
          getAgentRunsForMetrics(),
          getAgents({
            status: 'active',
            limit: 10,
            page: 1,
          }),
          getRecentAgentRuns(),
        ]);

        // Process metrics
        const successRate = calculateSuccessRate(runsData);
        const avgRuntime = calculateAvgRuntime(runsData);
        const totalCost = calculateTotalCost(runsData);

        setMetrics({
          totalRuns,
          successRate,
          avgRuntime,
          totalCost,
        });

        // Process agents
        const agentList = Array.isArray(agentsData) ? agentsData : agentsData.items;
        const activeAgents = agentList.filter((agent) => agent.disabled === 0);
        setAgents(activeAgents.slice(0, 10));

        // Set agent runs
        setAgentRuns(recentRuns);
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
      } finally {
        setMetricsLoading(false);
        setAgentsLoading(false);
        setAgentRunsLoading(false);
      }
    }

    fetchAllData();
  }, []);

  const metricsData = [
    {
      id: 'total-runs',
      title: 'Total Agent Runs',
      subtitle: 'Last 7 days',
      value: metricsLoading ? '...' : formatNumber(metrics.totalRuns),
      tooltip: 'Total number of agent executions in the last 7 days',
    },
    {
      id: 'success-rate',
      title: 'Success Rate',
      subtitle: 'Last 7 days',
      value: metricsLoading ? '...' : `${metrics.successRate.toFixed(1)}%`,
      tooltip: 'Percentage of successful agent runs without errors',
    },
    {
      id: 'avg-runtime',
      title: 'Avg Runtime',
      subtitle: 'Last 7 days',
      value: metricsLoading ? '...' : formatDuration(metrics.avgRuntime),
      tooltip: 'Average execution time across all agent runs',
    },
    {
      id: 'cost',
      title: 'Total Cost',
      subtitle: 'Last 7 days',
      value: metricsLoading ? '...' : formatCurrency(metrics.totalCost),
      tooltip: 'Total API costs for LLM usage across all agents',
    },
  ];

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        {/* HUF Page head */}
        <div>
          <h1 className="font-display font-bold text-[38px] uppercase text-ink leading-none tracking-tight">
            Dashboard
          </h1>
          <p className="font-body text-steel text-[14px] mt-1">
            Monitor your agents, flows, and system performance
          </p>
        </div>

        {/* HUF Gauge Strip — single bordered instrument strip, not 4 floating cards */}
        <TooltipProvider>
          <div className="border border-ink flex divide-x divide-line">
            {metricsData.map((metric, i) => (
              <div key={metric.id} className={cn('flex-1 p-4', i === metricsData.length - 1 && 'border-r-0')}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px] uppercase tracking-widest text-steel">
                    {metric.title}
                  </span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-3.5 w-3.5 text-steel-soft cursor-help" strokeWidth={1.6} />
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="max-w-xs font-mono text-[11px]">{metric.tooltip}</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div className="font-mono text-[9.5px] text-steel-soft mb-2">{metric.subtitle}</div>
                <div className={cn(
                  'font-display font-bold text-[38px] leading-none',
                  metric.id === 'cost' ? 'text-signal-ink' : 'text-ink',
                )}>
                  {metricsLoading && metric.value === '...' ? (
                    <Loader2 className="w-5 h-5 animate-spin text-steel" />
                  ) : (
                    metric.value
                  )}
                </div>
                {metric.id === 'cost' && !metricsLoading && (
                  <span className="font-mono text-[9px] text-signal-ink">↑ flagged</span>
                )}
              </div>
            ))}
          </div>
        </TooltipProvider>

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
            <ActiveAgentsTab agents={agents} loading={agentsLoading} />
          </TabsContent>

          {/* Flows Tab */}
          <TabsContent value="flows" className="space-y-4">
            <ActiveFlowsTab />
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
