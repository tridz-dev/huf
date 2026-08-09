export type CapabilityKind = "resource" | "action" | "event" | "schedule" | "workflow" | "report";

export type CapabilitySourceType = "declared" | "framework_discovered" | "generated" | "inferred";

export type MutationLevel = "read" | "write" | "destructive" | "unknown";

export type CapabilityVisibility = "recommended" | "normal" | "advanced" | "hidden";

export type CapabilityActionability = "actionable_now" | "informational" | "requires_adapter" | "requires_app_declaration";

/**
 * JSON-Schema-shaped parameter description, as emitted by
 * huf.ai.capabilities.actions for action capabilities.
 */
export interface CapabilityParametersSchema {
  type?: string;
  properties?: Record<string, { type?: string; description?: string }>;
  required?: string[];
}

export interface CapabilityParameter {
  name: string;
  type: string;
  required: boolean;
  default?: unknown;
  description?: string;
}

export interface CapabilityDescriptor {
  id: string;
  kind: CapabilityKind;
  source_app: string;
  source_type: CapabilitySourceType;
  source_key: string;
  title: string;
  short_description?: string;
  description?: string;
  category?: string;
  resource_doctype?: string;
  function_path?: string;
  event_name?: string;
  hook_name?: string;
  /** Either a flat parameter list or a JSON-Schema object; normalize before rendering. */
  parameters_schema?: CapabilityParameter[] | CapabilityParametersSchema;
  payload_schema?: Record<string, unknown>;
  return_schema?: Record<string, unknown>;
  read_only?: boolean;
  mutation_level: MutationLevel;
  required_permission?: string;
  allow_guest?: boolean;
  confidence: number;
  relevance_score: number;
  visibility: CapabilityVisibility;
  actionability: CapabilityActionability;
  metadata?: Record<string, unknown>;
}

export interface CapabilityApp {
  app: string;
  title: string;
  huf_app_id?: string | null;
  has_manifest: boolean;
}

export interface CapabilityResourceDetail {
  doctype: string;
  title: string;
  fields_summary?: string;
  generated_actions: CapabilityDescriptor[];
  generated_events: CapabilityDescriptor[];
  related_resources?: string[];
  permissions?: {
    read?: boolean;
    write?: boolean;
    create?: boolean;
    submit?: boolean;
    cancel?: boolean;
  };
}
