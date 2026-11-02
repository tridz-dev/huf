/**
 * Required argument names per tool, learned from the tool list the builder loads.
 * Validation uses it so a tool step cannot be saved without the inputs its schema requires,
 * for every tool and not only the preset cards.
 */
import { getFlowTools } from '../../services/toolApi';

const requiredByTool = new Map<string, string[]>();
let loading: Promise<void> | null = null;

export function registerToolSchemas(tools: Array<{ name: string; params_json_schema?: Record<string, unknown> }>): void {
  for (const t of tools) {
    const req = t.params_json_schema?.required;
    requiredByTool.set(t.name, Array.isArray(req) ? (req as string[]) : []);
  }
}

export function requiredInputsFor(toolId: string): string[] {
  return requiredByTool.get(toolId) ?? [];
}

/** Load the tool list once so validation knows every tool's required inputs. */
export function ensureToolSchemasLoaded(): Promise<void> {
  if (!loading) {
    loading = getFlowTools()
      .then((list) => registerToolSchemas(list || []))
      .catch(() => {
        loading = null;
      });
  }
  return loading;
}
