import { useState } from 'react';
import { formatAbsoluteTime } from '@/lib/serverTime';
import { formatTimeAgo } from '@/utils/time';

export function DocFieldValue({ field }: { field: { key: string; value: string; full?: string } }) {
    const [open, setOpen] = useState(false);
    if (!field.full) return <>{field.value}</>;
    return (
        <>
            <span data-testid={`flow-run-document-value-${field.key}`}>{open ? field.full : field.value}</span>{' '}
            <button
                type="button"
                className="text-xs font-medium text-primary underline"
                data-testid={`flow-run-document-more-${field.key}`}
                onClick={() => setOpen((v) => !v)}
            >
                {open ? 'Show less' : 'Show more'}
            </button>
        </>
    );
}

/** Engine errors name the node id and the internal edge rule; show the step title and the actual reason. */
export function readableRunError(message: string, labelOf: (id?: string | null) => string): string {
    const m = /^Node '([^']+)' of type '[^']+' failed and declares no on_error successor: ([\s\S]*)$/.exec(message);
    return m ? `${labelOf(m[1])} failed: ${m[2]}` : message;
}

export function TimeValue({ value }: { value: string | null | undefined }) {
    if (!value) return <span className="text-muted-foreground">Not available</span>;
    return (
        <span title={formatTimeAgo(value)}>
            {formatAbsoluteTime(value)}
        </span>
    );
}
