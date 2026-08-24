/**
 * Meeting Recorder API
 *
 * Thin wrappers around the Phase 2 whitelisted backend methods in
 * `huf.ai.meetings.meeting_api` and `huf.ai.meetings.meeting_recording`.
 * Every function here returns the already-unwrapped `response.message`
 * payload (never the raw axios/frappe-sdk envelope), throws a normalized
 * error via `handleFrappeError` on failure, and does no caching/derived
 * state of its own — that lives in `useMeetingRecorder` and the pages that
 * call these functions.
 */

import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
  Meeting,
  MeetingListItem,
  MeetingRecordingChunk,
  MeetingStatus,
} from '@/types/meeting.types';

const API_PREFIX = 'huf.ai.meetings.meeting_api';
const RECORDING_PREFIX = 'huf.ai.meetings.meeting_recording';

export interface CreateMeetingParams {
  title?: string;
  description?: string;
  participants?: string;
}

export interface CreateMeetingResult {
  meeting_name: string;
}

export async function createMeeting(params: CreateMeetingParams = {}): Promise<CreateMeetingResult> {
  try {
    const response = await call.post(`${API_PREFIX}.create_meeting`, params);
    return response.message as CreateMeetingResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface RecordingLifecycleResult {
  meeting_name: string;
  status: MeetingStatus;
  started_at?: string;
  stopped_at?: string;
}

export async function startRecording(meetingName: string): Promise<RecordingLifecycleResult> {
  try {
    const response = await call.post(`${API_PREFIX}.start_recording`, { meeting_name: meetingName });
    return response.message as RecordingLifecycleResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function pauseRecording(meetingName: string): Promise<RecordingLifecycleResult> {
  try {
    const response = await call.post(`${API_PREFIX}.pause_recording`, { meeting_name: meetingName });
    return response.message as RecordingLifecycleResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function resumeRecording(meetingName: string): Promise<RecordingLifecycleResult> {
  try {
    const response = await call.post(`${API_PREFIX}.resume_recording`, { meeting_name: meetingName });
    return response.message as RecordingLifecycleResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function stopRecording(meetingName: string): Promise<RecordingLifecycleResult> {
  try {
    const response = await call.post(`${API_PREFIX}.stop_recording`, { meeting_name: meetingName });
    return response.message as RecordingLifecycleResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface UpdateMeetingContextParams {
  meetingName: string;
  title?: string;
  description?: string;
  participants?: string;
}

export interface UpdateMeetingContextResult {
  meeting_name: string;
  title?: string;
  description?: string;
  participants?: string;
  context_completed: 0 | 1;
}

export async function updateMeetingContext(
  params: UpdateMeetingContextParams,
): Promise<UpdateMeetingContextResult> {
  try {
    const response = await call.post(`${API_PREFIX}.update_meeting_context`, {
      meeting_name: params.meetingName,
      title: params.title,
      description: params.description,
      participants: params.participants,
    });
    return response.message as UpdateMeetingContextResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface GetMeetingResult {
  meeting: Meeting;
  chunks: MeetingRecordingChunk[];
}

export async function getMeeting(meetingName: string): Promise<GetMeetingResult> {
  try {
    const response = await call.post(`${API_PREFIX}.get_meeting`, { meeting_name: meetingName });
    return response.message as GetMeetingResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface ListMeetingsParams {
  start?: number;
  limit?: number;
  status?: MeetingStatus;
  search?: string;
}

export interface ListMeetingsResult {
  meetings: MeetingListItem[];
  has_more: boolean;
}

export async function listMeetings(params: ListMeetingsParams = {}): Promise<ListMeetingsResult> {
  try {
    const response = await call.post(`${API_PREFIX}.list_meetings`, params);
    return response.message as ListMeetingsResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface RetryChunkTranscriptionResult {
  chunk_name: string;
  upload_status: string;
}

export async function retryChunkTranscription(chunkName: string): Promise<RetryChunkTranscriptionResult> {
  try {
    const response = await call.post(`${API_PREFIX}.retry_chunk_transcription`, { chunk_name: chunkName });
    return response.message as RetryChunkTranscriptionResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface RetrySummaryResult {
  meeting_name: string;
  status: MeetingStatus;
}

export async function retrySummary(meetingName: string): Promise<RetrySummaryResult> {
  try {
    const response = await call.post(`${API_PREFIX}.retry_summary`, { meeting_name: meetingName });
    return response.message as RetrySummaryResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface UploadChunkParams {
  meeting: string;
  sequence: number;
  clientStartedAt?: string;
  durationSeconds?: number;
  /** Exactly one of `audioB64` or `file` must be provided. */
  audioB64?: string;
  file?: string;
}

export interface UploadChunkResult {
  chunk_name: string;
  sequence: number;
  upload_status: string;
  chunk_count: number;
}

/**
 * Uploads a single recorded audio segment for a meeting. Callers own retry
 * policy (see `useMeetingRecorder`) — this function makes exactly one
 * network attempt and rejects on failure so the caller can back off.
 */
export async function uploadChunk(params: UploadChunkParams): Promise<UploadChunkResult> {
  try {
    const response = await call.post(`${RECORDING_PREFIX}.upload_chunk`, {
      meeting: params.meeting,
      sequence: params.sequence,
      client_started_at: params.clientStartedAt,
      duration_seconds: params.durationSeconds,
      audio_b64: params.audioB64,
      file: params.file,
    });
    return response.message as UploadChunkResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
