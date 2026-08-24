/**
 * Meeting export downloads.
 *
 * Both backend endpoints (`huf.ai.meetings.meeting_export.download_transcript`
 * and `.download_minutes`) are Frappe "download" style whitelisted methods —
 * they set `frappe.response.type = "download"` server-side, so they must be
 * triggered via a direct browser navigation to the method URL (same-origin
 * session cookie auth applies automatically), not via `call.post`/axios.
 */

const FRAPPE_URL = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

const EXPORT_PREFIX = 'huf.ai.meetings.meeting_export';

function openExportUrl(method: string, meetingName: string): void {
  const url = `${FRAPPE_URL}/api/method/${EXPORT_PREFIX}.${method}?meeting_name=${encodeURIComponent(meetingName)}`;
  window.open(url, '_blank');
}

export function downloadMeetingTranscript(meetingName: string): void {
  openExportUrl('download_transcript', meetingName);
}

export function downloadMeetingMinutes(meetingName: string): void {
  openExportUrl('download_minutes', meetingName);
}
