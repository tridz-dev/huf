import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { usePageLayout } from '@/hooks/usePageLayout';
import { McpDetailsPage } from './McpDetailsPage';
import { getMCPServer } from '../services/mcpApi';
import { getAgent } from '../services/agentApi';

export { McpDetailsPageWrapper };
export default McpDetailsPageWrapper;

function McpDetailsPageWrapper() {
  const { mcpId } = useParams<{ mcpId: string }>();
  const [searchParams] = useSearchParams();
  const fromAgent = searchParams.get('agent');
  const [serverName, setServerName] = useState<string>('New MCP Server');
  const [agentLabel, setAgentLabel] = useState<string>('Agent');
  const isNew = mcpId === 'new';

  useEffect(() => {
    if (fromAgent) {
      getAgent(fromAgent)
        .then((agent) => {
          setAgentLabel(agent.agent_name || agent.name);
        })
        .catch(() => {
          setAgentLabel('Agent');
        });
    }
  }, [fromAgent]);

  useEffect(() => {
    if (mcpId && !isNew) {
      getMCPServer(mcpId).then((server) => {
        setServerName(server.server_name || server.name);
      }).catch((error) => {
        console.error('Error loading MCP server:', error);
        setServerName('MCP Server');
      });
    } else {
      setServerName('New MCP Server');
    }
  }, [mcpId, isNew]);

  const breadcrumbs = [
    ...(fromAgent
      ? [{ label: agentLabel, href: `/agents/${fromAgent}#tools` }]
      : []),
    { label: 'MCP Servers', href: '/mcp' },
    { label: serverName },
  ];

  usePageLayout({ breadcrumbs });

  return <McpDetailsPage />;
}
