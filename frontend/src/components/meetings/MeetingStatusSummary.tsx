import { useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { getMeetingStatusCounts } from '@/services/meetingApi';

interface MeetingStatusSummaryProps {
  onFilterClick: (status: string) => void;
  overviewVersion?: number;
}

interface StatusCounts {
  Recording?: number;
  Paused?: number;
  Stopped?: number;
  Transcribing?: number;
  Summarizing?: number;
  Failed?: number;
  Completed?: number;
}

/**
 * Summary strip of clickable status-count pills for the meetings list.
 * Renders 4 grouped status pills:
 * - Recording: sum of Recording + Paused counts
 * - Processing: sum of Stopped + Transcribing + Summarizing counts
 * - Failed: exact count
 * - Completed: exact count
 *
 * Refetches counts every 45s and on overviewVersion changes (debounced 4s trailing).
 * Does not render a Draft pill (not user-meaningful for this summary).
 */
export function MeetingStatusSummary({ onFilterClick, overviewVersion }: MeetingStatusSummaryProps) {
  const [counts, setCounts] = useState<StatusCounts | null>(null);

  // Guard against concurrent in-flight requests and track debounce timer
  const inFlightRef = useRef(false);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchCounts = async () => {
    // Skip if already fetching to avoid duplicate requests
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    try {
      const result = await getMeetingStatusCounts();
      setCounts(result);
    } catch (error) {
      // Fail silently — non-critical summary strip. Log for debugging.
      console.warn('Failed to fetch meeting status counts:', error);
      // Optionally render empty or show zeros on error — we choose not to render pills
    } finally {
      inFlightRef.current = false;
    }
  };

  // Effect 1: Initial fetch and 45s periodic refetch (fallback for stale states)
  useEffect(() => {
    // Fetch immediately on mount
    fetchCounts();

    // Refetch every 45 seconds regardless of live events
    const intervalId = setInterval(() => {
      fetchCounts();
    }, 45000);

    return () => {
      clearInterval(intervalId);
    };
  }, []);

  // Effect 2: Refetch on overviewVersion change, debounced 4s trailing
  useEffect(() => {
    if (overviewVersion === undefined) return;

    // Clear existing timeout to reset the 4s timer
    if (debounceTimeoutRef.current !== null) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // Set new timeout — only refetch after 4s of no new changes
    debounceTimeoutRef.current = setTimeout(() => {
      fetchCounts();
    }, 4000);

    return () => {
      // Clean up on unmount or when overviewVersion changes again
      if (debounceTimeoutRef.current !== null) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, [overviewVersion]);

  if (counts === null) {
    // During initial load, render nothing to avoid blocking the page
    return null;
  }

  // Calculate grouped counts
  const recordingCount = (counts.Recording ?? 0) + (counts.Paused ?? 0);
  const processingCount = (counts.Stopped ?? 0) + (counts.Transcribing ?? 0) + (counts.Summarizing ?? 0);
  const failedCount = counts.Failed ?? 0;
  const completedCount = counts.Completed ?? 0;

  // Pill data: label, count, status string for onFilterClick, badge variant, and whether to de-emphasize
  const pills = [
    {
      label: 'Recording',
      count: recordingCount,
      status: 'Recording',
      variant: 'pill-danger' as const,
      isZero: recordingCount === 0,
    },
    {
      label: 'Processing',
      count: processingCount,
      status: 'Processing',
      variant: 'pill-neutral' as const,
      isZero: processingCount === 0,
    },
    {
      label: 'Failed',
      count: failedCount,
      status: 'Failed',
      variant: 'pill-danger' as const,
      isZero: failedCount === 0,
    },
    {
      label: 'Completed',
      count: completedCount,
      status: 'Completed',
      variant: 'pill-success' as const,
      isZero: completedCount === 0,
    },
  ];

  return (
    <div className="flex gap-2 mb-6">
      {pills.map((pill) => (
        <button
          key={pill.status}
          onClick={() => onFilterClick(pill.status)}
          className={`flex items-center gap-1 transition-opacity ${
            pill.isZero ? 'opacity-50 hover:opacity-70' : 'opacity-100 hover:opacity-90'
          }`}
          title={`Filter by ${pill.label}`}
          type="button"
        >
          <Badge variant={pill.variant} className="px-3 py-1.5 text-[12px]">
            {pill.label}
            <span className="ml-1">·</span>
            <span className="ml-1 font-semibold">{pill.count}</span>
          </Badge>
        </button>
      ))}
    </div>
  );
}
