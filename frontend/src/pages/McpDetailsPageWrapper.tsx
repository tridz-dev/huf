import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { McpDetailsPage } from './McpDetailsPage';
import { getMCPServer } from '../services/mcpApi';

export function McpDetailsPageWrapper() {
  const { mcpId } = useParams<{ mcpId: string }>();
  const [serverName, setServerName] = useState<string>('New MCP Server');
  const isNew = mcpId === 'new';

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
    { label: 'MCP Servers', href: '/mcp' },
    { label: serverName },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <McpDetailsPage />
    </UnifiedLayout>
  );
}

