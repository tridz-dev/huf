/** A JSON Schema property of an app step's settings (the subset the form understands). */
export interface SchemaProp {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array';
  title?: string;
  description?: string;
  enum?: string[];
  items?: SchemaProp;
  properties?: Record<string, SchemaProp>;
  required?: string[];
  'x-huf-widget'?: 'data-ref' | 'doctype' | 'template';
}

/** A step type an installed app adds (huf.ai.flow.catalog.api.list_node_types). */
export interface AppNodeType {
  type: string;
  label: string;
  category: string;
  icon: string;
  description: string;
  config_schema: SchemaProp;
  app: string;
}

/** A row of the answer: app steps always; with `app`, also `{type, builtin: true}` for each allowed built-in. */
export type NodeTypeRow = AppNodeType & { builtin?: boolean };

export async function listNodeTypes(app?: string): Promise<NodeTypeRow[]> {
  // Loaded on use so the labels and icons that read this catalog do not pull in the SDK.
  const { call } = await import('@/lib/frappe-sdk');
  const result = await call.post('huf.ai.flow.catalog.api.list_node_types', app === undefined ? {} : { app });
  return (result.message ?? []) as NodeTypeRow[];
}
