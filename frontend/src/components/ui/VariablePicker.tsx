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
    onSelect: (variable: string) => void;
}

export function VariablePicker({ onSelect }: VariablePickerProps) {
    const { activeFlow } = useFlowContext();

    const variables = useMemo(() => {
        const vars = ['trigger_payload'];
        if (!activeFlow) return vars;

        activeFlow.nodes.forEach(node => {
            if (node.data.actionConfig) {
                const ac = node.data.actionConfig as any;
                if (ac.save_response_to_context) vars.push(ac.save_response_to_context);
                if (ac.save_result_to_context) vars.push(ac.save_result_to_context);
                if (ac.output?.save_result_to_context) vars.push(ac.output.save_result_to_context);
                if (ac.store_decision_in_context) vars.push(ac.store_decision_in_context);
            }
        });

        return [...new Set(vars)].filter(Boolean);
    }, [activeFlow]);

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="h-6 text-[10px] px-2 font-mono" title="Insert Variable">
                    {'{x}'} Variables
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-[200px] max-h-[300px] overflow-y-auto">
                <DropdownMenuLabel className="text-xs">Available Variables</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {variables.map(v => (
                    <DropdownMenuItem
                        key={v}
                        className="text-xs font-mono cursor-pointer"
                        onSelect={() => onSelect(`{{${v}}}`)}
                    >
                        {v}
                    </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                    className="text-xs text-muted-foreground italic cursor-pointer"
                    onSelect={() => onSelect(`{{context.}}`)}
                >
                    Custom...
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
