import { useEffect, useState } from 'react';
import { useSocket } from '../contexts/SocketContext';

/**
 * `meeting_processing_status` — emitted by
 * `huf.ai.meetings.meeting_transcription._emit_processing_status` (also used
 * from `meeting_summary.py`) on the `meeting:{meeting_name}` channel, scoped
 * to the meeting's owner. Mirrors `AgentRunStatusEvent` in `useChatSocket.tsx`.
 */
export type MeetingProcessingStatusEvent = {
    type: 'meeting_processing_status';
    meeting: string;
    status: 'Transcribing' | 'Summarizing' | 'Completed' | 'Failed';
    chunks_transcribed: number;
    chunks_total: number;
};

export type MeetingProcessingState = {
    status: MeetingProcessingStatusEvent['status'] | null;
    chunksTranscribed: number;
    chunksTotal: number;
};

const INITIAL_STATE: MeetingProcessingState = {
    status: null,
    chunksTranscribed: 0,
    chunksTotal: 0,
};

/**
 * Subscribes to realtime processing progress for a single meeting. Consumers
 * (e.g. `MeetingProcessingStatus`) read `{status, chunksTranscribed,
 * chunksTotal}`; nothing here polls the server — the state is purely
 * event-driven from the `meeting:{meetingName}` channel.
 */
export function useMeetingProcessingSocket(meetingName: string | null) {
    const socket = useSocket();
    const [state, setState] = useState<MeetingProcessingState>(INITIAL_STATE);

    useEffect(() => {
        setState(INITIAL_STATE);

        if (!socket || !meetingName) {
            return;
        }

        const handler = (data: MeetingProcessingStatusEvent) => {
            if (data.type !== 'meeting_processing_status') {
                return;
            }

            setState({
                status: data.status,
                chunksTranscribed: data.chunks_transcribed,
                chunksTotal: data.chunks_total,
            });
        };

        socket.on(`meeting:${meetingName}`, handler);

        return () => {
            socket.off(`meeting:${meetingName}`, handler);
        };
    }, [socket, meetingName]);

    return state;
}
