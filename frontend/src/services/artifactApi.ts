import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface ArtifactDoc {
  name: string;
  title?: string;
  artifact_type: string;
  language?: string;
  content: string;
  message?: string;
  message_index?: number;
  size_bytes?: number;
  creation?: string;
  conversation: string;
  content_hash?: string;
  agent?: string;
}

export async function getArtifact(name: string): Promise<ArtifactDoc> {
  try {
    const result = await call.get('huf.ai.artifact_api.get_artifact', { name });
    return (result?.message ?? result) as ArtifactDoc;
  } catch (error) {
    handleFrappeError(error, 'Error fetching artifact');
  }
}
