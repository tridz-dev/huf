import { toast } from '@/lib/toast';
import { flowService } from '../../services/flowService';
import type { Flow } from '../../types/flow.types';

export // Cheap equality check for flows to prevent unnecessary updates
function flowsEqual(a: Flow | null, b: Flow | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.id === b.id &&
    a.name === b.name &&
    a.description === b.description &&
    a.status === b.status &&
    a.category === b.category &&
    a.version === b.version &&
    a.nodes.length === b.nodes.length &&
    a.edges.length === b.edges.length
  );
}

/**
 * The "create a procedure from this flow on save" checkbox (if enabled) runs after the flow itself is saved and
 * leaves a note on the doc explaining what happened -- surface it so the user isn't left guessing. A missing
 * note (the checkbox was off) is silently skipped.
 */
export async function announceConversion(flowId: string): Promise<void> {
  try {
    const conversion = await flowService.getConversionStatus(flowId);
    if (conversion.conversion_note) {
      if (conversion.converted_procedure) {
        toast.success(conversion.conversion_note);
      } else {
        toast.info(conversion.conversion_note);
      }
    }
  } catch (conversionErr) {
    // Non-critical: the flow itself saved fine, just couldn't fetch the note.
    console.error('Failed to fetch flow conversion status:', conversionErr);
  }
}
