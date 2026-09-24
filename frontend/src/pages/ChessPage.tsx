import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useChessGame } from '@/hooks/useChessGame';
import { requestAgentMove } from '@/services/chessApi';
import { ChessBoardPanel } from '@/components/chess/ChessBoardPanel';
import { MoveList } from '@/components/chess/MoveList';
import { AgentStatusPanel } from '@/components/chess/AgentStatusPanel';
import { cn } from '@/lib/utils';

/**
 * ChessPage
 *
 * Orchestration layer for playing chess against the HUF Chess Player agent.
 * Manages game state, player moves, agent move flow with repair logic, and UI state.
 *
 * Layout: standalone full-page (no UnifiedLayout), with minimal top bar and
 * board/status/moves layout. Handles the complete agent move flow including:
 * 1. Triggering on player turn change
 * 2. Sending move request to agent
 * 3. Applying move with error/repair handling
 * 4. Displaying status and commentary
 */
export function ChessPage() {
	const navigate = useNavigate();

	// Game state via hook
	const [playerColor, setPlayerColor] = useState<'white' | 'black'>('white');
	const game = useChessGame(playerColor);

	// Agent move flow state
	const [isAgentThinking, setIsAgentThinking] = useState(false);
	const [agentComment, setAgentComment] = useState<string | undefined>(undefined);

	// Track error state for inline display (alternative to toast)
	const [agentError, setAgentError] = useState<string | undefined>(undefined);

	// Effect: trigger agent move when it becomes the agent's turn
	// Note: we suppress react-hooks/exhaustive-deps below on the dependency array
	// because we intentionally depend on specific extracted properties of the
	// game object rather than the entire game reference — game is a new object
	// literal every render, so depending on it directly would re-run this effect
	// (and its state-setting side effects) on every render, not just when the
	// values that actually matter change.
	useEffect(() => {
		// Only trigger if:
		// 1. It's the agent's turn (not player's turn)
		// 2. Game is still playing
		// 3. We're not already thinking
		if (game.isPlayerTurn || isAgentThinking || game.outcome.kind !== 'playing') {
			return;
		}

		// Determine agent's color (opposite of player)
		const agentColor: 'white' | 'black' = playerColor === 'white' ? 'black' : 'white';

		/**
		 * Attempt to apply agent move, with one repair round on failure.
		 * Returns 'success', or a failure reason distinguishing an API/permission/
		 * model-not-configured failure (requestAgentMove returned null) from a
		 * move-validation failure (the agent responded but the move was illegal) —
		 * these need different error messages regardless of move count or color,
		 * unlike a move-count-based heuristic which only covers one specific case.
		 */
		const tryAgentMove = async (
			params: Parameters<typeof requestAgentMove>[0]
		): Promise<'success' | 'unavailable' | 'invalid-move'> => {
			const response = await requestAgentMove(params);

			if (response === null) {
				return 'unavailable';
			}

			// Attempt to apply the move
			const success = game.applyAgentMove(response.move);
			if (success) {
				// Success! Update comment and return
				if (response.comment) {
					setAgentComment(response.comment);
				}
				return 'success';
			}

			// Move was invalid (shouldn't happen, but design accounts for it)
			return 'invalid-move';
		};

		const executeAgentMove = async () => {
			setIsAgentThinking(true);
			setAgentError(undefined);

			try {
				const params = {
					fen: game.fen,
					history: game.history,
					legalMoves: game.legalMoves,
					color: agentColor,
				};

				// First attempt
				const firstResult = await tryAgentMove(params);
				if (firstResult === 'success') {
					setIsAgentThinking(false);
					return;
				}

				// An 'unavailable' result means requestAgentMove itself failed (no
				// model configured, insufficient permission, rate limit, network) —
				// retrying immediately won't help, so skip the repair round and
				// surface the right message straight away.
				if (firstResult === 'unavailable') {
					setAgentError(
						"This game's AI opponent isn't available right now — no model may be configured, or you may not have permission to play"
					);
					toast.error('AI opponent unavailable');
					return;
				}

				// 'invalid-move': the agent responded but the move didn't validate —
				// this is what the one-repair-round is for.
				const repairResult = await tryAgentMove(params);
				if (repairResult === 'success') {
					setIsAgentThinking(false);
					return;
				}

				if (repairResult === 'unavailable') {
					setAgentError(
						"This game's AI opponent isn't available right now — no model may be configured, or you may not have permission to play"
					);
					toast.error('AI opponent unavailable');
				} else {
					setAgentError(
						"The opponent's move couldn't be validated — try again or resign"
					);
					toast.error('Opponent move validation failed');
				}
			} finally {
				setIsAgentThinking(false);
			}
		};

		executeAgentMove();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [
		game.isPlayerTurn,
		isAgentThinking,
		game.outcome.kind,
		playerColor,
		game.fen,
		game.history,
		game.legalMoves,
		game.applyAgentMove,
	]);

	/**
	 * Handle player move from the board.
	 */
	const handlePlayerMove = useCallback(
		(from: string, to: string, promotion?: string): boolean => {
			const success = game.applyPlayerMove(from, to, promotion);
			if (success) {
				setAgentError(undefined);
			}
			return success;
		},
		[game]
	);

	/**
	 * Start a new game.
	 */
	const handleNewGame = useCallback(
		(chosenColor: 'white' | 'black') => {
			setPlayerColor(chosenColor);
			game.newGame(chosenColor);
			setIsAgentThinking(false);
			setAgentComment(undefined);
			setAgentError(undefined);
		},
		[game]
	);

	/**
	 * Resign the game.
	 */
	const handleResign = useCallback(() => {
		game.resign();
		setAgentError(undefined);
	}, [game]);

	/**
	 * Retry agent move (user-initiated after error).
	 */
	const handleRetry = useCallback(() => {
		// Clear error and let the effect re-trigger by clearing agent-thinking state
		setAgentError(undefined);
		// The effect will detect it's the agent's turn and try again
	}, []);

	// Determine board orientation
	const boardOrientation = playerColor === 'white' ? 'white' : 'black';

	// Board is disabled if it's the agent's turn, agent is thinking, or game is over
	const boardDisabled = !game.isPlayerTurn || isAgentThinking || game.outcome.kind !== 'playing';

	return (
		<div className="h-screen w-screen flex flex-col bg-paper">
			{/* Top Bar */}
			<div className="flex items-center justify-between h-16 px-6 border-b border-line">
				<div className="flex items-center gap-4">
					<button
						onClick={() => navigate('/')}
						className="text-sm text-steel hover:text-ink transition-colors"
						aria-label="Back to home"
					>
						← Back
					</button>
					<h1 className="font-display text-[20px] font-bold tracking-tight">
						Chess
					</h1>
				</div>

				{/* New Game Button */}
				<div className="flex items-center gap-2">
					<button
						onClick={() => handleNewGame(playerColor)}
						className={cn(
							'px-4 py-2 rounded-[2px] border border-line',
							'bg-panel hover:bg-paper-deep transition-colors',
							'text-sm font-medium text-ink'
						)}
					>
						New game
					</button>
				</div>
			</div>

			{/* Main Content */}
			<div className="flex-1 overflow-hidden flex gap-6 p-6">
				{/* Board Panel (Left) */}
				<div className="flex-1 flex flex-col gap-2">
					<ChessBoardPanel
						fen={game.fen}
						boardOrientation={boardOrientation}
						disabled={boardDisabled}
						onPlayerMove={handlePlayerMove}
						needsPromotionChoice={game.needsPromotionChoice}
					/>

					{/* Color Selection (for new game) */}
					{game.outcome.kind !== 'playing' && (
						<div className="flex gap-2">
							<button
								onClick={() => handleNewGame('white')}
								className={cn(
									'flex-1 px-3 py-2 rounded-[2px] border border-line',
									'text-sm font-medium transition-colors',
									playerColor === 'white'
										? 'bg-good text-paper'
										: 'bg-panel hover:bg-paper-deep text-ink'
								)}
							>
								Play as White
							</button>
							<button
								onClick={() => handleNewGame('black')}
								className={cn(
									'flex-1 px-3 py-2 rounded-[2px] border border-line',
									'text-sm font-medium transition-colors',
									playerColor === 'black'
										? 'bg-good text-paper'
										: 'bg-panel hover:bg-paper-deep text-ink'
								)}
							>
								Play as Black
							</button>
						</div>
					)}
				</div>

				{/* Right Rail (Status, Moves, Comment) */}
				<div className="w-80 flex flex-col gap-4 overflow-y-auto">
					{/* Agent Status Panel */}
					<AgentStatusPanel
						outcome={game.outcome}
						isAgentThinking={isAgentThinking}
						agentComment={agentComment}
						playerColor={playerColor}
					/>

					{/* Error Message (if agent move failed) */}
					{agentError && (
						<div className="border border-signal-ink rounded-[2px] bg-panel p-3">
							<p className="text-sm text-signal-ink font-mono">{agentError}</p>
							<div className="flex gap-2 mt-2">
								<button
									onClick={handleRetry}
									className={cn(
										'flex-1 px-3 py-1 rounded-[2px] border border-line',
										'text-xs font-medium text-ink hover:bg-paper-deep transition-colors'
									)}
								>
									Retry
								</button>
								<button
									onClick={handleResign}
									className={cn(
										'flex-1 px-3 py-1 rounded-[2px] border border-line',
										'text-xs font-medium text-signal-ink hover:bg-paper-deep transition-colors'
									)}
								>
									Resign
								</button>
							</div>
						</div>
					)}

					{/* Resign Button (if game is playing and no error) */}
					{!agentError && game.outcome.kind === 'playing' && (
						<button
							onClick={handleResign}
							className={cn(
								'w-full px-3 py-2 rounded-[2px] border border-line',
								'text-sm font-medium text-signal-ink',
								'bg-panel hover:bg-paper-deep transition-colors'
							)}
						>
							Resign
						</button>
					)}

					{/* Move List */}
					<MoveList moves={game.moves} />
				</div>
			</div>
		</div>
	);
}

export default ChessPage;
