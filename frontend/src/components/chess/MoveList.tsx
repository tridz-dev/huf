import { cn } from '@/lib/utils';

interface MoveListProps {
	moves: string[];
}

/**
 * MoveList
 *
 * Displays the SAN move history in a bordered panel, organized as numbered pairs
 * ("1. e4 e5", "2. Nf3 Nc6", ...). If there's a trailing unpaired move (agent
 * hasn't responded yet), it's shown alone on its row.
 *
 * Styling:
 * - Panel: `--panel` background, 1px `--line` border, 2px radius
 * - Typeface: IBM Plex Mono (the canonical "data/notation" register)
 * - Move numbers: `--steel-soft` or `--steel`; moves: `--ink`
 * - Empty state: "No moves yet" in `--steel-soft`, IBM Plex Mono
 */
export function MoveList({ moves }: MoveListProps) {
	if (moves.length === 0) {
		return (
			<div className="border border-line rounded bg-panel p-4">
				<p className="font-mono text-sm text-steel-soft">No moves yet</p>
			</div>
		);
	}

	// Pair up moves: each row is "N. white black" or "N. white" if trailing
	const rows: Array<{ number: number; white: string; black?: string }> = [];
	for (let i = 0; i < moves.length; i += 2) {
		const moveNumber = Math.floor(i / 2) + 1;
		const white = moves[i];
		const black = moves[i + 1];

		rows.push({
			number: moveNumber,
			white,
			black,
		});
	}

	return (
		<div className="border border-line rounded bg-panel">
			<div className="overflow-y-auto max-h-96 p-3 space-y-2">
				{rows.map((row) => (
					<div
						key={row.number}
						className={cn(
							'font-mono text-sm leading-relaxed',
							'text-ink'
						)}
					>
						<span className="text-steel-soft">{row.number}.</span>
						{' '}
						<span>{row.white}</span>
						{row.black && (
							<>
								{' '}
								<span>{row.black}</span>
							</>
						)}
					</div>
				))}
			</div>
		</div>
	);
}
