export interface DecisionAnswer {
  status?: string;
  current_node_id?: string | null;
}

/**
 * True when the server's answer to an approve / reject shows the run moved on: it left "Waiting Approval",
 * or it is waiting at a later approval step. A success toast is only shown for such an answer; an answer
 * that still shows the run waiting at the step that was decided means the decision was not recorded.
 */
export function decisionMovedRun(answer: DecisionAnswer | null | undefined, stepDecided: string | null | undefined): boolean {
  if (!answer || !answer.status) return false;
  if (answer.status !== 'Waiting Approval') return true;
  return !!stepDecided && !!answer.current_node_id && answer.current_node_id !== stepDecided;
}
