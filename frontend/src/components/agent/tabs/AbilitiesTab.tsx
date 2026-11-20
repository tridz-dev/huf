/**
 * AbilitiesTab (AF-3, composition state 4): Knowledge + Actions as ToggleRow
 * lists, and a collapsed "Skills, MCP servers, procedures" group.
 *
 * Switch semantics (the data model has no per-row `enabled` except on MCP):
 *  - MCP row: switch = Agent MCP Server.enabled (onToggleMCP).
 *  - Tool row: no enabled flag exists, so switch = attached or not. It is
 *    always on for a listed row; switching it off calls onRemoveTool.
 *  - Knowledge row: same rule, off calls onRemoveKnowledge(index).
 *
 * Capability map (every capability of the old tabs stays reachable):
 *  Add tool modal / create tool (inside the modal) -> "Add tool" -> onAddTools
 *  Edit tool -> row menu "Edit" -> onEditTool;  Remove -> menu/switch
 *  Connect / create MCP -> "Connect MCP server" -> onAddMCP;  Sync -> row menu -> onSyncMCP
 *  Add / edit / remove knowledge -> onAddKnowledge / onEditKnowledge / onRemoveKnowledge
 *  Create knowledge source -> "Create a new source" -> onCreateKnowledge
 *  Knowledge mode (Mandatory = Always include, Optional = Search when relevant)
 *     -> row menu "Change mode" dialog with PresetSelector -> onKnowledgeModeChange
 *  Skills (add/mode/priority/description/remove) -> SkillsTab inside the advanced group
 *  Procedures -> ProcedureBindingsTab inside the advanced group
 */
import { useState } from 'react';
import { BookOpen, Edit, ExternalLink, Plug, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { FormSection, PresetSelector } from '@/components/builder';
import { OverflowMenu, SettingsAdvanced, type Tone } from '@/components/patterns';
import { ToggleRow } from '@/components/builder';
import type { AgentKnowledgeRow, AgentToolFunctionRef } from '@/types/agent.types';
import type { MCPServerRef } from '@/services/mcpApi';
import type { AgentSkillRow } from '@/types/skill.types';
import { getToolIconForType } from '../../tools/toolIconMap';
import { SkillsTab } from '../SkillsTab';
import { ProcedureBindingsTab } from '../ProcedureBindingsTab';

export type KnowledgeState = 'ready' | 'failed' | 'empty';
export interface KnowledgeStatus { state: KnowledgeState; text?: string }

export interface AbilitiesTabProps {
  knowledgeSources: AgentKnowledgeRow[];
  /** Keyed by AgentKnowledgeRow.knowledge_source. Missing = no status line. */
  knowledgeStatus?: Record<string, KnowledgeStatus>;
  onAddKnowledge: () => void;
  onEditKnowledge: (index: number) => void;
  onRemoveKnowledge: (index: number) => void;
  onCreateKnowledge?: () => void;
  onKnowledgeModeChange?: (index: number, mode: AgentKnowledgeRow['mode']) => void;

  selectedTools: AgentToolFunctionRef[];
  onAddTools: () => void;
  onRemoveTool: (toolId: string) => void;
  onEditTool?: (toolId: string) => void;
  mcpServers?: MCPServerRef[];
  onAddMCP?: () => void;
  onRemoveMCP?: (serverId: string) => void;
  onToggleMCP?: (serverId: string, enabled: boolean) => void;
  onSyncMCP?: (serverId: string) => void;
  mcpLoading?: boolean;
  /** System agent + non-admin: tool attach/detach read-only. */
  locked?: boolean;

  skills: AgentSkillRow[];
  skillOptions: { value: string; label: string; subtitle?: string }[];
  onSkillsChange: (skills: AgentSkillRow[]) => void;
  /** Procedure bindings need a saved agent. */
  agentId?: string;
}

const isOn = (v: boolean | number | undefined) => v === undefined || v === true || v === 1;

const KNOWLEDGE_TONE: Record<KnowledgeState, { tone: Tone; text: string }> = {
  ready: { tone: 'ready', text: 'Ready' },
  failed: { tone: 'error', text: 'Failed to index' },
  empty: { tone: 'attention', text: 'Empty' },
};

const MODE_PRESETS = [
  { value: 'Optional', label: 'Search when relevant', description: 'Looks things up only when a question needs it', recommended: true },
  { value: 'Mandatory', label: 'Always include', description: 'Added to every answer' },
];
export const knowledgeModeLabel = (mode: string) => (mode === 'Mandatory' ? 'Always include' : 'Search when relevant');

export function AbilitiesTab(p: AbilitiesTabProps) {
  const [modeIndex, setModeIndex] = useState<number | null>(null);
  const mcp = p.mcpServers ?? [];
  const editing = modeIndex !== null ? p.knowledgeSources[modeIndex] : undefined;

  return (
    <div className="space-y-6">
      <FormSection
        title="Knowledge"
        description="Documents it can answer from."
        actions={<Button type="button" size="sm" variant="outline" onClick={p.onAddKnowledge}><Plus className="mr-1.5 h-4 w-4" />Add knowledge</Button>}
      >
        {p.knowledgeSources.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line p-6 text-center">
            <p className="text-ui-text text-steel">No knowledge yet. Add a source so it can answer from your documents.</p>
            {p.onCreateKnowledge && <Button type="button" variant="ghost" size="sm" className="mt-2" onClick={p.onCreateKnowledge}>Create a new source</Button>}
          </div>
        ) : (
          <div className="rounded-lg border border-line">
            {p.knowledgeSources.map((ks, i) => {
              const st = p.knowledgeStatus?.[ks.knowledge_source];
              const meta = st ? KNOWLEDGE_TONE[st.state] : undefined;
              return (
                <ToggleRow
                  key={ks.name || `ks-${i}`}
                  icon={<BookOpen className="h-4 w-4" />}
                  title={ks.knowledge_source}
                  description={knowledgeModeLabel(ks.mode)}
                  status={meta ? (st?.text ?? meta.text) : undefined}
                  statusTone={meta?.tone}
                  checked
                  onCheckedChange={(on) => { if (!on) p.onRemoveKnowledge(i); }}
                  actions={
                    <OverflowMenu label={`More actions for ${ks.knowledge_source}`} items={[
                      { label: 'Change mode', icon: BookOpen, onSelect: () => setModeIndex(i), disabled: !p.onKnowledgeModeChange },
                      { label: 'Edit', icon: Edit, onSelect: () => p.onEditKnowledge(i) },
                      { label: 'Remove', icon: Trash2, destructive: true, separated: true, onSelect: () => p.onRemoveKnowledge(i) },
                    ]} />
                  }
                />
              );
            })}
          </div>
        )}
        {p.knowledgeSources.length > 0 && p.onCreateKnowledge && (
          <Button type="button" variant="ghost" size="sm" onClick={p.onCreateKnowledge}>Create a new source</Button>
        )}
      </FormSection>

      <FormSection
        title="Actions"
        description="Things it can do: tools and connected servers."
        actions={
          <div className="flex items-center gap-2">
            <Button asChild size="sm" variant="ghost"><Link to="/integrations"><ExternalLink className="mr-1.5 h-3.5 w-3.5" />Browse integrations</Link></Button>
            {p.onAddMCP && <Button type="button" size="sm" variant="outline" onClick={p.onAddMCP} disabled={p.mcpLoading}><Plug className="mr-1.5 h-4 w-4" />Connect MCP server</Button>}
            <Button type="button" size="sm" variant="outline" onClick={p.onAddTools} disabled={p.locked}><Plus className="mr-1.5 h-4 w-4" />Add tool</Button>
          </div>
        }
      >
        {p.selectedTools.length + mcp.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line p-6 text-center">
            <p className="text-ui-text text-steel">No actions yet. Add tools to let it look up data, call APIs or use other agents.</p>
          </div>
        ) : (
          <div className="rounded-lg border border-line">
            {p.selectedTools.map((tool) => {
              const Icon = getToolIconForType(tool.types, tool.service, tool.tool_type);
              const name = tool.tool_name || tool.name;
              return (
                <ToggleRow
                  key={`tool-${tool.name}`}
                  icon={<Icon className="h-4 w-4" />}
                  title={name}
                  description={tool.description || undefined}
                  status="Attached"
                  statusTone="ready"
                  checked
                  disabled={p.locked}
                  onCheckedChange={(on) => { if (!on) p.onRemoveTool(tool.name); }}
                  actions={
                    <OverflowMenu label={`More actions for ${name}`} items={[
                      ...(p.onEditTool ? [{ label: 'Edit', icon: Edit, onSelect: () => p.onEditTool?.(tool.name) }] : []),
                      { label: 'Remove', icon: Trash2, destructive: true, separated: !!p.onEditTool, disabled: p.locked, onSelect: () => p.onRemoveTool(tool.name) },
                    ]} />
                  }
                />
              );
            })}
            {mcp.map((m) => {
              const serverOff = m.mcp_enabled !== undefined && !isOn(m.mcp_enabled);
              const name = m.server_name || m.mcp_server;
              return (
                <ToggleRow
                  key={`mcp-${m.name}`}
                  icon={<Plug className="h-4 w-4" />}
                  title={name}
                  description={[m.description, m.tool_count ? `${m.tool_count} tools` : ''].filter(Boolean).join(' · ') || m.server_url}
                  status={serverOff ? 'Server disabled' : isOn(m.enabled) ? 'Connected' : 'Off'}
                  statusTone={serverOff ? 'attention' : isOn(m.enabled) ? 'ready' : 'off'}
                  checked={isOn(m.enabled)}
                  disabled={p.mcpLoading || serverOff}
                  onCheckedChange={(on) => p.onToggleMCP?.(m.name, on)}
                  actions={
                    <OverflowMenu label={`More actions for ${name}`} items={[
                      { label: 'Sync tools', icon: RefreshCw, disabled: p.mcpLoading || serverOff, onSelect: () => p.onSyncMCP?.(m.name) },
                      { label: 'Remove', icon: Trash2, destructive: true, separated: true, disabled: p.mcpLoading, onSelect: () => p.onRemoveMCP?.(m.name) },
                    ]} />
                  }
                />
              );
            })}
          </div>
        )}
      </FormSection>

      <SettingsAdvanced label="Skills, MCP servers, procedures">
        <SkillsTab skills={p.skills} skillOptions={p.skillOptions} onChange={p.onSkillsChange} />
        <ProcedureBindingsTab agentId={p.agentId} />
      </SettingsAdvanced>

      <Dialog open={editing !== undefined} onOpenChange={(o) => { if (!o) setModeIndex(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>How should it use {editing?.knowledge_source}?</DialogTitle>
            <DialogDescription>You can change this any time.</DialogDescription>
          </DialogHeader>
          {editing && modeIndex !== null && (
            <PresetSelector label="Knowledge mode" presets={MODE_PRESETS} value={editing.mode}
              onChange={(v) => { p.onKnowledgeModeChange?.(modeIndex, v as AgentKnowledgeRow['mode']); setModeIndex(null); }} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
