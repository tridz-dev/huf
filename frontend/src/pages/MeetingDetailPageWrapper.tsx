import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { MeetingDetailPage } from './MeetingDetailPage';
import { getMeeting } from '../services/meetingApi';
import { formatTimeAgo } from '../utils/time';

export { MeetingDetailPageWrapper };
export default MeetingDetailPageWrapper;

function MeetingDetailPageWrapper() {
  const { meetingId } = useParams<{ meetingId: string }>();
  const [meetingLabel, setMeetingLabel] = useState<string>('Meeting');

  useEffect(() => {
    if (!meetingId) return;
    getMeeting(meetingId)
      .then(({ meeting }) => {
        setMeetingLabel(meeting.title?.trim() || `Meeting — ${formatTimeAgo(meeting.started_at || meeting.creation)}`);
      })
      .catch(() => {
        setMeetingLabel('Meeting');
      });
  }, [meetingId]);

  const breadcrumbs = [
    { label: 'Meetings', href: '/meetings' },
    { label: meetingLabel },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <MeetingDetailPage />
    </UnifiedLayout>
  );
}
