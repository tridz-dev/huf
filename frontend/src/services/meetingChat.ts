/**
 * Meeting Chat API
 *
 * Thin wrappers around the whitelisted backend methods in
 * `huf.ai.meetings.meeting_chat` — "chat to get info out of the meeting" and
 * "revise the summary with a prompt" (a tiny, minimal alternative to
 * Firefly). Mirrors meetingApi.ts's conventions exactly, with one
 * deliberate difference: `askMeeting`/`reviseSummary` returning an
 * `{ error }` payload is an EXPECTED, non-exceptional outcome — the backend
 * deliberately doesn't throw on model-call failures so the UI can render an
 * inline chat-bubble error. Only real `call.post` exceptions (HTTP/network
 * failures) go through `handleFrappeError`/rethrow here.
 */

import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { MeetingChatMessage } from '@/types/meeting.types';

const API_PREFIX = 'huf.ai.meetings.meeting_chat';

export interface AskMeetingResult {
  reply?: string;
  error?: string;
  message_name?: string;
}

export async function askMeeting(meetingName: string, message: string): Promise<AskMeetingResult> {
  try {
    const response = await call.post(`${API_PREFIX}.ask_meeting`, {
      meeting_name: meetingName,
      message,
    });
    return response.message as AskMeetingResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface ReviseSummaryResult {
  summary?: string;
  error?: string;
}

export async function reviseSummary(meetingName: string, instruction: string): Promise<ReviseSummaryResult> {
  try {
    const response = await call.post(`${API_PREFIX}.revise_summary`, {
      meeting_name: meetingName,
      instruction,
    });
    return response.message as ReviseSummaryResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function getChatHistory(meetingName: string): Promise<MeetingChatMessage[]> {
  try {
    const response = await call.post(`${API_PREFIX}.get_chat_history`, { meeting_name: meetingName });
    return response.message as MeetingChatMessage[];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
