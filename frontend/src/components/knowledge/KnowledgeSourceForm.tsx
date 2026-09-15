import type { ReactNode } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Form } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { GeneralTab } from './GeneralTab';
import { StatusTab } from './StatusTab';
import type { KnowledgeSourceFormValues } from './types';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import type { AIProvider } from '@/types/agent.types';

/**
 * Field/label metadata for the tabs rendered by KnowledgeSourceForm.
 * Shared between the standalone route page (which drives its own tab
 * validation via createFormSubmitHandler) and any embedded usage.
 */
export const knowledgeSourceTabConfig = {
  general: {
    label: 'General',
    fields: [
      'source_name',
      'description',
      'knowledge_type',
      'scope',
      'storage_mode',
      'chunk_size',
      'chunk_overlap',
      'embedding_model',
      'vector_dimension',
      'embedding_provider',
      'chroma_mode',
      'chroma_host',
      'chroma_port',
      'chroma_ssl',
      'pgvector_connection_mode',
      'pgvector_table_name',
      'pgvector_distance_metric',
      'pgvector_index_type',
      'pgvector_host',
      'pgvector_port',
      'pgvector_database',
      'pgvector_user',
      'pgvector_password',
      'pgvector_sslmode',
      'advanced_config',
    ],
    default: true,
  },
  status: {
    label: 'Status',
    fields: [] as string[],
    default: false,
  },
} as const;

export function parseAdvancedConfig(value: unknown): Record<string, unknown> {
  if (typeof value === 'string' && value.trim()) {
    try {
      return JSON.parse(value) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

export function stringifyAdvancedConfig(value: Record<string, unknown> | undefined): string {
  return JSON.stringify(value || {});
}

export function mapDocToFormValues(doc: Partial<KnowledgeSourceDoc>): KnowledgeSourceFormValues {
  return {
    source_name: doc.source_name || '',
    description: doc.description || '',
    knowledge_type: doc.knowledge_type || 'sqlite_fts',
    scope: doc.scope || 'Site',
    storage_mode: doc.storage_mode || 'Frappe File',
    chunk_size: doc.chunk_size ?? 512,
    chunk_overlap: doc.chunk_overlap ?? 50,
    disabled: doc.disabled === 1,
    embedding_model: doc.embedding_model || '',
    vector_dimension: doc.vector_dimension ?? 1536,
    embedding_provider: doc.embedding_provider || '',
    chroma_mode: doc.chroma_mode || 'File',
    chroma_host: doc.chroma_host || 'localhost',
    chroma_port: doc.chroma_port ?? 8000,
    chroma_ssl: doc.chroma_ssl === 1,
    pgvector_connection_mode: doc.pgvector_connection_mode || 'External PostgreSQL',
    pgvector_table_name: doc.pgvector_table_name || 'huf_knowledge_vectors',
    pgvector_distance_metric: doc.pgvector_distance_metric || 'cosine',
    pgvector_index_type: doc.pgvector_index_type || 'hnsw',
    pgvector_host: doc.pgvector_host || 'localhost',
    pgvector_port: doc.pgvector_port ?? 5432,
    pgvector_database: doc.pgvector_database || '',
    pgvector_user: doc.pgvector_user || '',
    pgvector_password: doc.pgvector_password || '',
    pgvector_sslmode: doc.pgvector_sslmode || 'prefer',
    advanced_config: parseAdvancedConfig(doc.advanced_config),
  };
}

/**
 * Maps validated form values to the API payload shape expected by
 * createKnowledgeSource / updateKnowledgeSource.
 */
export function buildKnowledgeSourcePayload(
  values: KnowledgeSourceFormValues,
): Partial<KnowledgeSourceDoc> {
  return {
    source_name: values.source_name,
    description: values.description || '',
    knowledge_type: values.knowledge_type,
    scope: values.scope,
    storage_mode: values.storage_mode as KnowledgeSourceDoc['storage_mode'],
    chunk_size: values.chunk_size,
    chunk_overlap: values.chunk_overlap,
    disabled: values.disabled ? 1 : 0,
    embedding_model: values.embedding_model || '',
    vector_dimension: values.vector_dimension ?? 1536,
    embedding_provider: values.embedding_provider || '',
    chroma_mode: values.chroma_mode,
    chroma_host: values.chroma_host || '',
    chroma_port: values.chroma_port ?? 8000,
    chroma_ssl: values.chroma_ssl ? 1 : 0,
    pgvector_connection_mode: values.pgvector_connection_mode,
    pgvector_table_name: values.pgvector_table_name || 'huf_knowledge_vectors',
    pgvector_distance_metric: values.pgvector_distance_metric,
    pgvector_index_type: values.pgvector_index_type,
    pgvector_host: values.pgvector_host || '',
    pgvector_port: values.pgvector_port ?? 5432,
    pgvector_database: values.pgvector_database || '',
    pgvector_user: values.pgvector_user || '',
    pgvector_password: values.pgvector_password || '',
    pgvector_sslmode: values.pgvector_sslmode,
    advanced_config: stringifyAdvancedConfig(values.advanced_config),
  };
}

interface KnowledgeSourceFormProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  isNew: boolean;
  providers: AIProvider[];
  /** Only relevant when showStatusTab is true (existing sources). */
  sourceDoc?: KnowledgeSourceDoc | null;
  /** Standalone page shows General + Status tabs; the create modal only needs General. */
  showStatusTab?: boolean;
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onSubmit: (e?: any) => void | Promise<void>;
  /** Rendered inside the <form> so Enter-to-submit and layout stay consistent. */
  footer?: ReactNode;
  className?: string;
  /** Wraps the tab/field content (e.g. DialogScrollBody for a modal). Identity by default. */
  bodyWrapper?: (children: ReactNode) => ReactNode;
}

/**
 * Presentational knowledge-source form body: field groups + validation,
 * shared by the standalone /knowledge/:id route page and the in-context
 * agent-editor create modal. Callers own data loading, submission side
 * effects (navigation, linking, toasts), and page/dialog chrome.
 */
export function KnowledgeSourceForm({
  form,
  isNew,
  providers,
  sourceDoc = null,
  showStatusTab = true,
  activeTab = 'general',
  onTabChange,
  onSubmit,
  footer,
  className = 'space-y-6',
  bodyWrapper = (children) => children,
}: KnowledgeSourceFormProps) {
  const content = showStatusTab ? (
    <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
      <TabsList layout="grid" cols={2}>
        <TabsTrigger value="general">{knowledgeSourceTabConfig.general.label}</TabsTrigger>
        <TabsTrigger value="status" disabled={isNew}>
          {knowledgeSourceTabConfig.status.label}
        </TabsTrigger>
      </TabsList>

      <TabsContent value="general" className="space-y-4">
        <GeneralTab form={form} isNew={isNew} providers={providers} />
      </TabsContent>

      <TabsContent value="status" className="space-y-4">
        <StatusTab source={sourceDoc} />
      </TabsContent>
    </Tabs>
  ) : (
    <GeneralTab form={form} isNew={isNew} providers={providers} />
  );

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className={className}>
        {bodyWrapper(content)}
        {footer}
      </form>
    </Form>
  );
}
