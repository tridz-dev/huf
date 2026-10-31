/** The business result of a finished run: an End step's own outcome, or what an approver decided. */
export interface RunOutcome {
    label: string;
    tone: 'good' | 'neutral' | 'bad';
}

/** What the run page needs to know about a step beyond its title (step type, loop body). */
export interface RunStepMeta {
    type: string;
    body?: string[];
    outcome?: RunOutcome;
}

/** Fields the run list and the run details both carry, for the run story. */
export interface RunStoryFields {
    /** A code approval behind a Waiting Code run has passed its expiry (display only; the row stays Pending). */
    approval_lapsed?: boolean;
    started_by?: string | null;
    started_by_name?: string | null;
    /** The run's place in its flow's history, oldest first. */
    run_number?: number | null;
    outcome?: RunOutcome | null;
}
