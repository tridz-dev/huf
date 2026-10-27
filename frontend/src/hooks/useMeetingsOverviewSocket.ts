import { useEffect, useState } from 'react';
import { useSocket } from '../contexts/SocketContext';
import type { MeetingProcessingStatusEvent } from './useMeetingProcessingSocket';

/**
 * Broadcast event for meetings overview — emitted by
 * `huf.ai.meetings.meeting_transcription._emit_processing_status` to the
 * `meetings_overview_status` channel (fixed per-user, scoped to the owner).
 * Carries the same payload shape as `meeting_processing_status` but is list-level,
 * not scoped to a single meeting; subscribers receive updates for all meetings
 * and can overlay live progress on the meetings list without per-meeting subscriptions.
 */
export const MEETINGS_OVERVIEW_EVENT = 'meetings_overview_status';

/**
 * State for a single meeting's live processing status from the overview event.
 */
export type MeetingOverviewStatus = {
	status: MeetingProcessingStatusEvent['status'];
	chunksTranscribed: number;
	chunksTotal: number;
};

/**
 * Subscribes to realtime processing progress for all meetings in the list.
 * Maintains a Map keyed by meeting name, updated on each event without
 * per-meeting subscribe/unsubscribe churn as pages load. Consumers
 * (e.g. `MeetingCard`) can read `overview.get(meetingName)` to overlay
 * live status + chunk counts on list rows, and can `useEffect` on the Map
 * reference or version counter to trigger debounced refetches of aggregate
 * counts elsewhere.
 */
export function useMeetingsOverviewSocket() {
	const socket = useSocket();
	const [overview, setOverview] = useState<Map<string, MeetingOverviewStatus>>(new Map());
	const [version, setVersion] = useState(0);

	useEffect(() => {
		if (!socket) {
			return;
		}

		const handler = (data: MeetingProcessingStatusEvent) => {
			if (data.type !== 'meeting_processing_status') {
				return;
			}

			setOverview((prevMap) => {
				const newMap = new Map(prevMap);
				newMap.set(data.meeting, {
					status: data.status,
					chunksTranscribed: data.chunks_transcribed,
					chunksTotal: data.chunks_total,
				});
				return newMap;
			});

			setVersion((v) => v + 1);
		};

		socket.on(MEETINGS_OVERVIEW_EVENT, handler);

		return () => {
			socket.off(MEETINGS_OVERVIEW_EVENT, handler);
		};
	}, [socket]);

	return { overview, version };
}
