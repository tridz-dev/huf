/**
 * Chat (gateway) trigger contract: node config and the registry the server serves.
 * Mirrors `huf/ai/flow/gateways/registry.py` and `graph_ir.schema.json` (GatewayTriggerConfig). FROZEN: a change to
 * these shapes needs coordinator approval (a JSON snapshot test pins the server side).
 */

export type GatewayTriggerNodeType = 'trigger.gateway' | 'trigger.whatsapp' | 'trigger.telegram';

/** A stored filter value. Arrays hold words only; the server caps lengths (see `GatewayRegistry.limits`). */
export type GatewayParamValue = string | number | boolean | string[] | null;

export interface GatewayParam {
  /** A registry param key, `^[a-z][a-z0-9_]*$`. */
  key: string;
  value: GatewayParamValue;
}

/** `config` of all three trigger nodes. `gateway` may be blank in a draft; publishing requires it. */
export interface GatewayTriggerConfig {
  gateway?: string;
  params?: GatewayParam[];
}

export type GatewayParamType =
  | 'text' | 'textarea' | 'select' | 'multiselect' | 'boolean' | 'number' | 'tags' | 'people';

export interface GatewayOption {
  value: string;
  label: string;
}

export interface GatewayParamSpec {
  key: string;
  label: string;
  help: string;
  type: GatewayParamType;
  options: GatewayOption[];
  required: boolean;
  default: GatewayParamValue;
  multiple: boolean;
  /** Show this option only while another option has one of these values. */
  show_when: { key: string; in: string[] } | null;
  section: 'setup' | 'more';
}

export type GatewayPayloadType = 'text' | 'number' | 'yes_no' | 'list' | 'datetime' | 'record';

export interface GatewayPayloadField {
  /** Always `input.<name>`: `input` is the single data contract for every trigger. */
  path: string;
  label: string;
  type: GatewayPayloadType;
  sample: unknown;
  /** Typed by the outside person: treat as untrusted. */
  customer_provided: boolean;
  sensitive: boolean;
  /** Hidden in the data picker until "Show advanced". */
  advanced: boolean;
}

export interface GatewayTriggerSpec {
  provider: string;
  label: string;
  node_type: GatewayTriggerNodeType;
  event_kinds: GatewayOption[];
  params: GatewayParamSpec[];
  payload_fields: GatewayPayloadField[];
  sample_payload: Record<string, unknown>;
}

export interface GatewayChoice {
  name: string;
  label: string;
  provider: string;
  enabled: boolean;
  connection_state: string;
}

/** Response of `huf.ai.flow.gateway_trigger_api.get_gateway_trigger_registry`. */
export interface GatewayRegistry {
  version: number;
  limits: { max_params: number; max_list_items: number; max_text: number; max_item_text: number };
  specs: Record<GatewayTriggerNodeType, GatewayTriggerSpec>;
  gateways: GatewayChoice[];
}
