import { useMemo } from 'react';
import { useFlowContext } from '../../contexts/FlowContext';
import { Button } from './button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from './dropdown-menu';

interface VariablePickerProps {
    /**
     * Called with a reference path (`input`, `trigger`, or a step id) and a short name that is safe
     * to use as a `{placeholder}` in a prompt.
     */
    onSelect: (reference: string, suggestedName: string) => void;
    /** Step the field belongs to (excluded from the list: a step cannot read its own result). */
    currentNodeId?: string | null;
    testId?: string;
}

function toPlaceholder(label: string, fallback: string): string {
    const cleaned = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    return /^[a-z_]/.test(cleaned) ? cleaned : fallback;
}

/** Lets the user pick data from the trigger or an earlier step instead of typing a reference path. */
export function VariablePicker({ onSelect, currentNodeId, testId = 'flow-variable-picker' }: VariablePickerProps) {
    const { activeFlow } = useFlowContext();

    const entries = useMemo(() => {
        const list: Array<{ ref: string; label: string; name: string }> = [
            { ref: 'input', label: 'Trigger input', name: 'input' },
            { ref: 'trigger', label: 'Trigger details', name: 'trigger' },
        ];
        for (const node of activeFlow?.nodes ?? []) {
            if (node.id === currentNodeId || node.data.nodeType !== 'action') continue;
            list.push({ ref: node.id, label: `Result of "${node.data.label}"`, name: toPlaceholder(node.data.label, node.id) });
        }
        return list;
    }, [activeFlow, currentNodeId]);

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="h-6 text-[10px] px-2" title="Insert data from an earlier step" data-testid={testId}>
                    Insert data
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-[220px] max-h-[300px] overflow-y-auto">
                <DropdownMenuLabel className="text-xs">Data you can use</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {entries.map((e) => (
                    <DropdownMenuItem
                        key={e.ref}
                        className="text-xs cursor-pointer"
                        data-testid={`${testId}-item-${e.ref}`}
                        onSelect={() => onSelect(e.ref, e.name)}
                    >
                        {e.label}
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
