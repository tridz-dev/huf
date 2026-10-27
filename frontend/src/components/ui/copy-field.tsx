import { useId, useState } from 'react';
import { Check, Copy, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { copyText } from '@/lib/clipboard';

export interface CopyFieldProps {
	label: string;
	value: string;
	/** Hide the value behind dots until the user presses Show. */
	masked?: boolean;
}


export function CopyField({ label, value, masked = false }: CopyFieldProps) {
	const id = useId();
	const [revealed, setRevealed] = useState(false);
	const [copied, setCopied] = useState(false);
	const hidden = masked && !revealed;

	const copy = async () => {
		if (await copyText(value)) {
			setCopied(true);
			toast.success('Copied');
			setTimeout(() => setCopied(false), 1500);
		} else {
			toast.error("Couldn't copy. Select the text and copy it yourself.");
		}
	};

	return (
		<div className="space-y-1.5">
			<Label htmlFor={id}>{label}</Label>
			<div className="flex items-center gap-2">
				<Input
					id={id}
					readOnly
					type={hidden ? 'password' : 'text'}
					value={value}
					title={hidden ? undefined : value}
					onFocus={(e) => e.currentTarget.select()}
					className="min-w-0 flex-1 truncate font-mono text-xs"
				/>
				{masked && (
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={() => setRevealed((r) => !r)}
						aria-label={`${revealed ? 'Hide' : 'Show'} ${label}`}
					>
						{revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
						{revealed ? 'Hide' : 'Show'}
					</Button>
				)}
				<Button type="button" variant="outline" size="icon" onClick={copy} aria-label={`Copy ${label}`}>
					{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
				</Button>
			</div>
		</div>
	);
}
