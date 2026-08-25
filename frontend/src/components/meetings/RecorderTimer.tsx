interface RecorderTimerProps {
  elapsedSeconds: number;
  paused?: boolean;
}

function formatClock(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const pad = (value: number) => value.toString().padStart(2, '0');
  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

/** Large monospaced timer — the dominant element on the recorder view
 * (PLAN.md G.1 "Recorder UX"). Visually freezes (dimmed) while paused. */
export function RecorderTimer({ elapsedSeconds, paused }: RecorderTimerProps) {
  return (
    <div
      className={`font-mono text-6xl font-semibold tabular-nums tracking-tight text-ink transition-opacity sm:text-7xl ${
        paused ? 'opacity-50' : 'opacity-100'
      }`}
    >
      {formatClock(elapsedSeconds)}
    </div>
  );
}
