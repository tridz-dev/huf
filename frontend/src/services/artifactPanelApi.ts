import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Compact artifact summary used by the right-side "Artifacts" panel in the
 * chat UI. Backed by the read-only `list_conversation_artifacts` whitelisted
 * method, which intentionally omits `content` (see huf.ai.artifact_api) since
 * the panel only ever needs to list, not render, artifacts.
 */
export interface ArtifactListItem {
  name: string;
  title?: string;
  artifact_type: string;
  language?: string;
  message: string;
  message_index: number;
  size_bytes: number;
  creation: string;
}

/**
 * Fetch the artifacts/docs/images generated or attached in a conversation.
 *
 * Degrades gracefully by design: the panel is a secondary affordance and
 * must never block chat rendering, so any failure (including the
 * PermissionError the backend raises for a conversation the caller doesn't
 * own) resolves to an empty list rather than throwing. Errors are still
 * logged via handleFrappeError so they remain visible in devtools.
 */
export async function listConversationArtifacts(
  conversation: string
): Promise<ArtifactListItem[]> {
  try {
    const result = await call.get('huf.ai.artifact_api.list_conversation_artifacts', {
      conversation,
    });
    const artifacts = result?.message ?? result;
    return Array.isArray(artifacts) ? (artifacts as ArtifactListItem[]) : [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation artifacts');
    return [];
  }
}

/**
 * Export an artifact to PDF or DOCX format.
 *
 * Degrades gracefully by design: export is a secondary action in the panel,
 * so any failure resolves to null rather than throwing. The caller should
 * handle null gracefully (e.g., show a transient toast). Errors are logged
 * via handleFrappeError so they remain visible in devtools.
 */
export async function exportArtifactFromPanel(
  name: string,
  format: 'pdf' | 'docx'
): Promise<{ file_url: string; format: string } | null> {
  try {
    const result = await call.get('huf.ai.artifact_export_api.export_artifact', {
      name,
      format,
    });
    return (result?.message ?? result) as { file_url: string; format: string };
  } catch (error) {
    handleFrappeError(error, 'Error exporting artifact');
    return null;
  }
}
