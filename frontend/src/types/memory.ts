export interface MemoryRecord {
  name: string;
  title: string;
  record_type: string;
  scope_type: string;
  scope_key: string;
  visibility: string;
  status: string;
  summary_text: string;
  confidence: number;
  importance_score: number;
  tags: string;
  agent?: string;
  conversation?: string;
  knowledge_source?: string;
  projection_status?: string;
  modified: string;
}
