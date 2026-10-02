import type { GameOutcome } from '@/hooks/useChessGame';

interface AgentStatusPanelProps {
	outcome: GameOutcome;
	isAgentThinking: boolean;
	agentComment?: string;
	playerColor: 'white' | 'black';
}

/**
 * AgentStatusPanel
 *
 * Displays the current game status and agent state using the canonical dot + mono
 * label vocabulary from DESIGN.md §7. States, in priority order:
 *
 * 1. Terminal state (outcome.kind !== 'playing'):
 *    - Checkmate: "Checkmate — you win" or "Checkmate — HUF Chess Player wins"
 *    - Stalemate: "Stalemate"
 *    - Draw: "Draw — [reason]" (derives from outcome.reason)
 *    - Resigned: "You resigned"
 *    Rendered in `--signal-ink` colored mono text (no dot), matching the HELD convention.
 *
 * 2. Agent thinking (isAgentThinking === true):
 *    - Dot: `background-color: var(--signal)` with `animate-blink` animation
 *    - Label: "Thinking…" in IBM Plex Mono, `--ink`
 *
 * 3. Player's turn (outcome.kind === 'playing' && turn === playerColor):
 *    - Dot: static `background-color: var(--good)`
 *    - Label: "Your move" in IBM Plex Mono, `--ink`
 *
 * 4. Waiting for agent (outcome.kind === 'playing' && turn !== playerColor):
 *    - Dot: static `background-color: var(--steel-soft)`
 *    - Label: "Waiting for opponent" in IBM Plex Mono, `--ink`
 *
 * Optional agent comment (if present, non-empty, and game not terminal):
 * - Quoted: `"{agentComment}"` in IBM Plex Sans, `--steel`
 */
export function AgentStatusPanel({
	outcome,
	isAgentThinking,
	agentComment,
	playerColor,
}: AgentStatusPanelProps) {
	// Derive current turn from outcome
	const gameIsPlaying = outcome.kind === 'playing';
	const isPlayerTurn =
		gameIsPlaying &&
		((playerColor === 'white' && outcome.kind === 'playing') ||
			(playerColor === 'black' && outcome.kind === 'playing'));

	// Terminal state messages
	const getTerminalMessage = (): string | null => {
		if (outcome.kind === 'checkmate') {
			const playerWon = outcome.winner === playerColor;
			return playerWon
				? 'Checkmate — you win'
				: 'Checkmate — HUF Chess Player wins';
		}

		if (outcome.kind === 'stalemate') {
			return 'Stalemate';
		}

		if (outcome.kind === 'draw') {
			const reasonMap: Record<string, string> = {
				'insufficient-material': 'Draw — insufficient material',
				'threefold-repetition': 'Draw — threefold repetition',
				'fifty-move': 'Draw — fifty-move rule',
				other: 'Draw',
			};
			return reasonMap[outcome.reason] || 'Draw';
		}

		if (outcome.kind === 'resigned') {
			return 'You resigned';
		}

		return null;
	};

	const terminalMessage = getTerminalMessage();

	// Status rendering
	const renderStatus = () => {
		// Terminal state: colored text, no dot
		if (terminalMessage) {
			return (
				<div className="font-mono text-sm text-signal-ink font-medium">
					{terminalMessage}
				</div>
			);
		}

		// Agent thinking: blinking dot + label
		if (isAgentThinking) {
			return (
				<div className="flex items-center gap-2">
					<span
						className="inline-flex items-center justify-center h-2 w-2 rounded-full animate-blink"
						style={{ backgroundColor: 'var(--signal)' }}
						aria-hidden
					/>
					<span className="font-mono text-sm text-ink">Thinking…</span>
				</div>
			);
		}

		// Player's turn: static dot (good color) + label
		if (isPlayerTurn) {
			return (
				<div className="flex items-center gap-2">
					<span
						className="inline-flex items-center justify-center h-2 w-2 rounded-full"
						style={{ backgroundColor: 'var(--good)' }}
						aria-hidden
					/>
					<span className="font-mono text-sm text-ink">Your move</span>
				</div>
			);
		}

		// Waiting for opponent: static dot (steel-soft) + label
		return (
			<div className="flex items-center gap-2">
				<span
					className="inline-flex items-center justify-center h-2 w-2 rounded-full"
					style={{ backgroundColor: 'var(--steel-soft)' }}
					aria-hidden
				/>
				<span className="font-mono text-sm text-ink">
					Waiting for opponent
				</span>
			</div>
		);
	};

	return (
		<div className="space-y-2">
			{/* Status line */}
			<div>{renderStatus()}</div>

			{/* Agent comment (if present and game not terminal) */}
			{!terminalMessage && agentComment && agentComment.trim() && (
				<div className="text-sm text-steel italic">
					"{agentComment}"
				</div>
			)}
		</div>
	);
}
