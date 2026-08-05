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

export async function getArtifactHtml(name: string): Promise<string> {
  try {
    const result = await call.get('huf.ai.artifact_export_api.get_artifact_html', { name });
    return (result?.message ?? result) as string;
  } catch (error) {
    handleFrappeError(error, 'Error rendering artifact');
  }
}

/**
 * Render UNSAVED document content (still being composed, or parsed inline
 * from a chat message that has no durable Artifact row) as self-contained
 * HTML. Unlike getArtifactHtml this sends the content itself rather than a
 * name, so it can be a sizeable body — use the POST-style call helper.
 */
export async function previewDocumentHtml(
  content: string,
  language: string = 'markdown',
  title: string = ''
): Promise<string> {
  try {
    const result = await call.post('huf.ai.artifact_export_api.preview_document_html', {
      content,
      language,
      title,
    });
    return (result?.message ?? result) as string;
  } catch (error) {
    handleFrappeError(error, 'Error rendering document preview');
  }
}

export async function exportArtifact(
  name: string,
  format: 'pdf' | 'docx' | 'html'
): Promise<{ file_url: string; format: string }> {
  try {
    const result = await call.get('huf.ai.artifact_export_api.export_artifact', {
      name,
      format,
    });
    return (result?.message ?? result) as { file_url: string; format: string };
  } catch (error) {
    handleFrappeError(error, 'Error exporting artifact');
  }
}
