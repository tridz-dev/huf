/**
 * Types for the Meeting Recorder feature.
 *
 * Mirrors the `Meeting` and `Meeting Recording Chunk` DocTypes
 * (huf/huf/doctype/meeting/meeting.json,
 * huf/huf/doctype/meeting_recording_chunk/meeting_recording_chunk.json)
 * and the payload shapes returned by `huf.ai.meetings.meeting_api` /
 * `huf.ai.meetings.meeting_recording` (Phase 2 backend).
 */

/** `Meeting.status` Select options, in lifecycle order. */
export type MeetingStatus =
  | 'Draft'
  | 'Recording'
  | 'Paused'
  | 'Stopped'
  | 'Transcribing'
  | 'Summarizing'
  | 'Completed'
  | 'Failed';

/** `Meeting Recording Chunk.upload_status` Select options. */
export type ChunkUploadStatus =
  | 'Pending'
  | 'Uploaded'
  | 'Transcribing'
  | 'Transcribed'
  | 'Failed';

/** Full `Meeting` document shape (all fields from meeting.json). */
export interface Meeting {
  name: string;
  title?: string;
  description?: string;
  participants?: string;
  status: MeetingStatus;
  started_at?: string;
  stopped_at?: string;
  duration_seconds?: number;
  chunk_count?: number;
  transcript?: string;
  transcript_language?: string;
  summary?: string;
  summary_agent_run?: string;
  context_prompted_at?: string;
  context_completed?: 0 | 1;
  failed_step?: 'Model Not Configured' | 'Transcription' | 'Summary' | '';
  last_error?: string;
  error_log?: string;
  is_system_owned?: 0 | 1;
  modified?: string;
  creation?: string;
  owner?: string;
}

/** `Meeting Chat Message.role` Select options. */
export type MeetingChatRole = 'user' | 'assistant';

/** Full `Meeting Chat Message` row shape (huf/huf/doctype/meeting_chat_message). */
export interface MeetingChatMessage {
  name: string;
  role: MeetingChatRole;
  content: string;
  applied_to_summary?: 0 | 1;
  error?: string;
  creation?: string;
}

/** Summary row shape returned inline by `list_meetings`. */
export interface MeetingListItem {
  name: string;
  title?: string;
  description?: string;
  status: MeetingStatus;
  started_at?: string;
  stopped_at?: string;
  duration_seconds?: number;
  chunk_count?: number;
  summary?: string;
  modified?: string;
}

/** Full `Meeting Recording Chunk` row shape as returned by `get_meeting`. */
export interface MeetingRecordingChunk {
  name: string;
  sequence: number;
  audio_file?: string;
  upload_status: ChunkUploadStatus;
  client_started_at?: string;
  duration_seconds?: number;
  transcript_text?: string;
  transcription_error?: string;
  retry_count?: number;
}
