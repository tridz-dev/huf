/**
 * Abilities state for the agent form: tools, MCP servers, knowledge and skills are local
 * until the page saves them with their sections. Also owns the modals those lists open.
 */
import { useMemo, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { SelectToolsModal, SelectMCPServersModal } from '@/components/tools';
import { ToolFormModal } from '@/components/tools/ToolFormModal';
import type { ToolFormData } from '@/types/toolTemplate.types';
import { AgentKnowledgeModal } from '../AgentKnowledgeModal';
import { getToolFunction, updateToolFunction } from '@/services/toolApi';
import { syncMCPTools, type MCPServerDoc, type MCPServerRef } from '@/services/mcpApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentKnowledgeRow, AgentToolFunctionRef, ToolType } from '@/types/agent.types';
import type { AgentSkillRow } from '@/types/skill.types';
import { knowledgeRows, mcpRows, sig, skillRows, toolRows } from './agentFormModel';

export interface AbilitiesSnapshot {
  tools: AgentToolFunctionRef[];
  mcp: MCPServerRef[];
  knowledge: AgentKnowledgeRow[];
  skills: AgentSkillRow[];
}

const toolsSig = (tools: AgentToolFunctionRef[], mcp: MCPServerRef[]) =>
  sig([[...toolRows(tools)].map((t) => t.tool).sort(), [...mcpRows(mcp)].sort((a, b) => a.mcp_server.localeCompare(b.mcp_server))]);

export function useAgentAbilities(opts: { agentId?: string; navigate: (to: string) => void }) {
  const { agentId, navigate } = opts;
  const [tools, setTools] = useState<AgentToolFunctionRef[]>([]);
  const [mcp, setMcp] = useState<MCPServerRef[]>([]);
  const [knowledge, setKnowledge] = useState<AgentKnowledgeRow[]>([]);
  const [skills, setSkills] = useState<AgentSkillRow[]>([]);
  const [saved, setSaved] = useState<AbilitiesSnapshot>({ tools: [], mcp: [], knowledge: [], skills: [] });
  const [mcpLoading, setMcpLoading] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [showMcp, setShowMcp] = useState(false);
  const [showKnowledge, setShowKnowledge] = useState(false);
  const [knowledgeIndex, setKnowledgeIndex] = useState<number | null>(null);
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [toolForm, setToolForm] = useState<Partial<ToolFormData> | null>(null);
  const [showToolForm, setShowToolForm] = useState(false);
  const [loadingTool, setLoadingTool] = useState(false);

  const dirty = useMemo(() => ({
    tools: toolsSig(tools, mcp) !== toolsSig(saved.tools, saved.mcp),
    knowledge: sig(knowledgeRows(knowledge)) !== sig(knowledgeRows(saved.knowledge)),
    skills: sig(skillRows(skills)) !== sig(skillRows(saved.skills)),
  }), [tools, mcp, knowledge, skills, saved]);

  const hydrate = (s: Partial<AbilitiesSnapshot>) => {
    if (s.tools) setTools(s.tools);
    if (s.mcp) setMcp(s.mcp);
    if (s.knowledge) setKnowledge(s.knowledge);
    if (s.skills) setSkills(s.skills);
    setSaved((cur) => ({ ...cur, ...s }));
  };
  const markSaved = (s: Partial<AbilitiesSnapshot>) => setSaved((cur) => ({ ...cur, ...s }));

  /** Rows a linked create-flow (knowledge / MCP) already persisted: add to both current and saved. */
  const addLinkedKnowledge = (row: AgentKnowledgeRow) => {
    const add = (p: AgentKnowledgeRow[]) => (p.some((k) => k.knowledge_source === row.knowledge_source) ? p : [...p, row]);
    setKnowledge(add);
    setSaved((c) => ({ ...c, knowledge: add(c.knowledge) }));
  };
  const addLinkedMcp = (server: MCPServerRef) => {
    const add = (p: MCPServerRef[]) => (p.some((s) => s.mcp_server === server.mcp_server) ? p : [...p, server]);
    setMcp(add);
    setSaved((c) => ({ ...c, mcp: add(c.mcp) }));
  };

  const requireAgent = (what: string, path: string) => {
    if (!agentId) { toast.error(`Please save the agent first before creating ${what}`); return; }
    navigate(`${path}?agent=${encodeURIComponent(agentId)}`);
  };

  const editTool = async (toolId: string) => {
    setEditingToolId(toolId);
    setLoadingTool(true);
    try {
      const t = await getToolFunction(toolId);
      if (t) {
        setToolForm({
          tool_name: t.tool_name, tool_type: t.tool_type, types: t.types as ToolType, description: t.description,
          reference_doctype: t.reference_doctype, agent: t.agent, function_path: t.function_path, function_name: t.function_name,
          pass_parameters_as_json: t.pass_parameters_as_json === 1, provider_app: t.provider_app, base_url: t.base_url,
          required_permission: t.required_permission, is_read_only: t.is_read_only === 1, allowed_for_guest: t.allowed_for_guest === 1,
          parameters: t.parameters || [], http_headers: t.http_headers || [],
        });
        setShowToolForm(true);
      }
    } catch (error) {
      console.error('Error loading tool:', error);
      toast.error(getFrappeErrorMessage(error) || 'Failed to load tool');
    } finally {
      setLoadingTool(false);
    }
  };

  const submitToolForm = async (data: ToolFormData) => {
    if (!editingToolId) return;
    try {
      await updateToolFunction(editingToolId, { ...data });
      setTools((cur) => cur.map((t) => (t.name === editingToolId ? { ...t, tool_name: data.tool_name, description: data.description, tool_type: data.tool_type } : t)));
      toast.success('Tool updated');
      setShowToolForm(false); setEditingToolId(null); setToolForm(null);
    } catch (error) {
      console.error('Error saving tool:', error);
      toast.error(getFrappeErrorMessage(error) || 'Failed to save tool');
    }
  };

  const syncMcp = async (serverId: string) => {
    const server = mcp.find((s) => s.name === serverId);
    if (!server) { toast.error('MCP server not found'); return; }
    setMcpLoading(true);
    try {
      const result = await syncMCPTools(server.mcp_server);
      if (result.success) {
        setMcp((cur) => cur.map((s) => (s.name === serverId ? { ...s, tool_count: result.tool_count ?? s.tool_count, last_sync: new Date().toISOString() } : s)));
        const n = result.tool_count ?? 0;
        toast.success(`Synced ${n} tool${n !== 1 ? 's' : ''} from MCP server`);
      } else {
        toast.error(result.error || 'Failed to sync MCP server tools');
      }
    } catch (error) {
      console.error('Error syncing MCP server:', error);
      toast.error(getFrappeErrorMessage(error) || 'Failed to sync MCP server tools');
    } finally {
      setMcpLoading(false);
    }
  };

  const addMcpServers = (servers: MCPServerDoc[]) => {
    const rows: MCPServerRef[] = servers.map((s) => ({
      name: `new:${s.name}`, mcp_server: s.name, server_name: s.server_name, description: s.description,
      server_url: s.server_url, enabled: true, mcp_enabled: s.enabled === 1, tool_count: 0,
    }));
    setMcp((cur) => [...cur, ...rows]);
  };

  const saveKnowledge = (row: AgentKnowledgeRow) =>
    setKnowledge((cur) => (knowledgeIndex !== null ? cur.map((k, i) => (i === knowledgeIndex ? row : k)) : [...cur, row]));

  /** Props for AbilitiesTab (minus statuses and skill options, which the page owns). */
  const tabProps = {
    knowledgeSources: knowledge,
    onAddKnowledge: () => { setKnowledgeIndex(null); setShowKnowledge(true); },
    onEditKnowledge: (i: number) => { setKnowledgeIndex(i); setShowKnowledge(true); },
    onRemoveKnowledge: (i: number) => setKnowledge((cur) => cur.filter((_, j) => j !== i)),
    onCreateKnowledge: () => requireAgent('knowledge', '/knowledge/new'),
    onKnowledgeModeChange: (i: number, mode: AgentKnowledgeRow['mode']) => setKnowledge((cur) => cur.map((k, j) => (j === i ? { ...k, mode } : k))),
    selectedTools: tools,
    onAddTools: () => setShowTools(true),
    onRemoveTool: (id: string) => setTools((cur) => cur.filter((t) => t.name !== id)),
    onEditTool: (id: string) => void editTool(id),
    mcpServers: mcp,
    onAddMCP: () => setShowMcp(true),
    onRemoveMCP: (id: string) => setMcp((cur) => cur.filter((s) => s.name !== id)),
    onToggleMCP: (id: string, enabled: boolean) => setMcp((cur) => cur.map((s) => (s.name === id ? { ...s, enabled } : s))),
    onSyncMCP: (id: string) => void syncMcp(id),
    mcpLoading,
    skills,
    onSkillsChange: setSkills,
  };

  const modals: ReactNode = (
    <>
      <SelectToolsModal open={showTools} onOpenChange={setShowTools} selectedTools={tools} onAddTools={(t) => setTools((cur) => [...cur, ...t])} />
      <SelectMCPServersModal
        open={showMcp} onOpenChange={setShowMcp}
        selectedServers={mcp.map((s) => ({
          name: s.mcp_server, server_name: s.server_name || '', description: s.description,
          enabled: ((s.mcp_enabled === true || s.mcp_enabled === 1) ? 1 : 0) as 0 | 1, server_url: s.server_url || '', transport_type: 'http' as const,
        })) as MCPServerDoc[]}
        onAddServers={addMcpServers}
        onCreateNew={() => requireAgent('MCP servers', '/mcp/new')} />
      <AgentKnowledgeModal open={showKnowledge} onOpenChange={setShowKnowledge} onSave={saveKnowledge}
        initialData={knowledgeIndex !== null ? knowledge[knowledgeIndex] : null}
        onCreateNew={() => requireAgent('knowledge', '/knowledge/new')} />
      <ToolFormModal open={showToolForm} onOpenChange={(o) => { setShowToolForm(o); if (!o) { setEditingToolId(null); setToolForm(null); } }}
        mode="edit" initialData={toolForm} onSubmit={submitToolForm} loading={loadingTool}
        toolName={editingToolId || undefined} currentAgentName={agentId} />
    </>
  );

  return { tools, mcp, knowledge, skills, dirty, hydrate, markSaved, addLinkedKnowledge, addLinkedMcp, tabProps, modals };
}
