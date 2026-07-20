/**
 * Dispatcher that renders a ParsedUIComponent using the appropriate
 * registered renderer.  Falls back to a formatted JSON display for
 * unknown types or data errors.
 */

import { AlertCircle } from 'lucide-react';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import type { ParsedUIComponent } from '@/types/artifact.types';
import { getUIComponentRenderer, getRegisteredComponentTypes } from './registry';

interface Props {
	component: ParsedUIComponent;
}

export function UIComponentRenderer({ component }: Props) {
	// Data-level error from parser
	if (component.error || !component.data) {
		return (
			<Alert variant="destructive" className="my-3">
				<AlertCircle className="size-4" />
				<AlertTitle>Component error</AlertTitle>
				<AlertDescription className="text-xs">
					<span className="font-mono">&lt;ui-component type=&quot;{component.type}&quot;&gt;</span>
					{' '}{component.error ?? 'Missing data'}
				</AlertDescription>
			</Alert>
		);
	}

	const Renderer = getUIComponentRenderer(component.type);

	if (!Renderer) {
		const known = getRegisteredComponentTypes().join(', ');
		return (
			<Alert className="my-3">
				<AlertCircle className="size-4" />
				<AlertTitle>Unknown component type: <code className="font-mono">{component.type}</code></AlertTitle>
				<AlertDescription className="text-xs space-y-2">
					<p>Registered types: {known}</p>
					<details>
						<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
							Show raw data
						</summary>
						<pre className="mt-1 overflow-x-auto rounded bg-muted p-2 text-[11px]">
							{JSON.stringify(component.data, null, 2)}
						</pre>
					</details>
				</AlertDescription>
			</Alert>
		);
	}

	return (
		<div className="my-3">
			<Renderer component={component} />
		</div>
	);
}
