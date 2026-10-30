/** What the "Use data" picker works with. Mirrors `huf/ai/flow/catalog/fields.py` (the server's answer). */

export type FieldType = 'text' | 'number' | 'yes_no' | 'date' | 'object' | 'list';

export interface ListInfo {
  count: number;
  item_type: FieldType;
  /** Short readable form of the first few items ("Tea", "Ada Lovelace"). */
  item_texts?: string[];
  /** Fields of one item; their `path` is relative to the item (`sku`). */
  item_fields: CatalogField[];
}

export interface CatalogField {
  /** Reference path the engine reads (`input.customer.name`); null when the name cannot be written as one (advanced only). */
  path: string | null;
  /** Plain name, "Customer > Name" for something inside another thing. */
  label: string;
  type: FieldType;
  /** The real value for a scalar; one short sentence for an object or a list. */
  sample?: string | number | boolean | null;
  list?: ListInfo;
  advanced_only?: boolean;
}

export type SampleSource = 'pinned' | 'last_run' | 'doctype' | 'none';

export interface CatalogStep {
  id: string;
  title: string;
  /** Graph type (`tool.call`, `trigger.webhook`...), used to pick an icon. */
  type: string;
  tool_id?: string | null;
  is_trigger: boolean;
  source: SampleSource;
  ran_at: string | null;
  fields: CatalogField[];
  has_sample: boolean;
  kind?: 'webhook' | 'schedule' | 'doc-event' | 'unset';
  last_request_available?: boolean;
  doctype?: string | null;
}

export interface CatalogLoop {
  id: string;
  title: string;
  items_path: string | null;
  item_fields: CatalogField[];
}

/** The answer of `huf.ai.flow.catalog.api.get_data_catalog`. */
export interface DataCatalog {
  flow_id: string;
  node_id: string;
  trigger: CatalogStep | null;
  steps: CatalogStep[];
  loop: CatalogLoop | null;
}

/** How a picked list or object is written into text. `undefined` = the value itself. */
export type PickMode = 'summary' | 'joined' | 'count';

/** One thing the person chose in the picker. */
export interface DataPick {
  /** Reference path to read. Never a bare `input` or `trigger`. */
  ref: string;
  /** Field name for the chip ("Customer name"). */
  label: string;
  /** Step the data comes from ("New order"). */
  stepTitle: string;
  stepId: string;
  mode?: PickMode;
}
