import { useMemo } from 'react';
import { useFlowContext } from '../../contexts/FlowContext';
import { availableReferences, type RefScope } from '../../lib/flowRefs';
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
     * Called with a reference path (`input`, `trigger`, `foreach.item` or a step id) and a short name that is
     * safe to use as a `{placeholder}` in a prompt or template.
     */
    onSelect: (reference: string, suggestedName: string) => void;
    /** Step the field belongs to: only the trigger and steps that always run before it are listed. */
    currentNodeId?: string | null;
    /** `loop-body`: the steps inside this loop (for a loop's "result to collect"). */
    scope?: RefScope;
    testId?: string;
    /** Accessible name; defaults to "Insert data". */
    label?: string;
}

/** Lets the user pick data from the trigger or an earlier step instead of typing a reference path. */
export function VariablePicker({ onSelect, currentNodeId, scope = 'ancestors', testId = 'flow-variable-picker', label }: VariablePickerProps) {
    const { activeFlow } = useFlowContext();

    const entries = useMemo(
        () => availableReferences(currentNodeId, activeFlow?.nodes ?? [], activeFlow?.edges ?? [], scope),
        [activeFlow, currentNodeId, scope]
    );

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2.5"
                    title="Insert data from the trigger or an earlier step"
                    aria-label={label ?? 'Insert data'}
                    data-testid={testId}
                >
                    Insert data
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-[240px] max-h-[300px] overflow-y-auto">
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
