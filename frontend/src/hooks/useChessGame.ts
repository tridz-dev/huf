/**
 * useChessGame
 *
 * Core chess game hook managing all chess.js state, game logic, and localStorage
 * persistence. Owns the complete game state (position, move history, outcome) and
 * provides the control interface for board interactions and agent move application.
 *
 * ## Game State Model
 *
 * `fen`: Current board position in Forsyth-Edwards Notation.
 * `moves`: Complete SAN move history, accumulated across the game.
 * `outcome`: Terminal game state (playing, checkmate, stalemate, draw variants, resigned).
 * `turn`: Whose turn it is ('white' or 'black', from chess.js's turn()).
 * `isPlayerTurn`: Derived from turn === playerColor and outcome.kind === 'playing'.
 * `legalMoves`: All legal moves in SAN format for the current position.
 *
 * ## localStorage Persistence
 *
 * On every successful move, `{playerColor, moves, fen}` is written to localStorage
 * under a fixed key. On hook mount, if a saved game exists, its `moves` are replayed
 * through a fresh chess.js instance to reconstruct state (crash/refresh recovery).
 * If replay fails, the localStorage entry is cleared and a fresh game starts.
 *
 * ## Outcome Priority Order
 *
 * After every move, outcome is derived in this order:
 * 1. chess.isCheckmate() → {kind: 'checkmate', winner: ...}
 * 2. chess.isStalemate() → {kind: 'stalemate'}
 * 3. chess.isInsufficientMaterial() → {kind: 'draw', reason: 'insufficient-material'}
 * 4. chess.isThreefoldRepetition() → {kind: 'draw', reason: 'threefold-repetition'}
 * 5. chess.isDrawByFiftyMoves() → {kind: 'draw', reason: 'fifty-move'}
 * 6. chess.isDraw() → {kind: 'draw', reason: 'other'}
 * 7. else {kind: 'playing'}
 *
 * ## Error Handling
 *
 * chess.js.move() throws on illegal moves (not null/false). All moves wrap in
 * try/catch. On application failure, state remains unchanged.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Chess, Move } from 'chess.js';

// ============================================================================
// Types
// ============================================================================

/**
 * Terminal game outcome states. Each variant carries the semantic information
 * the player needs to understand how the game ended.
 */
export type GameOutcome =
	| { kind: 'playing' }
	| { kind: 'checkmate'; winner: 'white' | 'black' }
	| { kind: 'stalemate' }
	| {
			kind: 'draw';
			reason:
				| 'insufficient-material'
				| 'threefold-repetition'
				| 'fifty-move'
				| 'other';
	  }
	| { kind: 'resigned'; by: 'player' };

interface UseChessGameReturn {
	/** Current board position in Forsyth-Edwards Notation */
	fen: string;
	/** Complete move history in SAN format */
	moves: string[];
	/** Terminal game state and outcome */
	outcome: GameOutcome;
	/** Whose turn it currently is */
	turn: 'white' | 'black';
	/** Whether it's the player's turn and the game is still playing */
	isPlayerTurn: boolean;
	/** All legal moves in SAN format for the current position */
	legalMoves: string[];
	/** Attempt a player move; returns true on success, false on failure */
	applyPlayerMove: (from: string, to: string, promotion?: string) => boolean;
	/** Check if a move from→to requires promotion choice before application */
	needsPromotionChoice: (from: string, to: string) => boolean;
	/** Apply a single SAN move from the agent; returns true on success */
	applyAgentMove: (san: string) => boolean;
	/** Resign the game as the player */
	resign: () => void;
	/** Start a fresh game with a new player color */
	newGame: (playerColor: 'white' | 'black') => void;
	/** Formatted move history string for agent prompt (e.g. "1. e4 e5 2. Nf3") */
	history: string;
}

// ============================================================================
// Constants
// ============================================================================

const LOCALSTORAGE_KEY = 'huf-chess-game';

// ============================================================================
// Utilities
// ============================================================================

/** Convert chess.js color ('w'/'b') to hook color ('white'/'black') */
function chessJsToHookColor(color: 'w' | 'b'): 'white' | 'black' {
	return color === 'w' ? 'white' : 'black';
}

/** Derive game outcome from current board state */
function deriveOutcome(chess: Chess): GameOutcome {
	// Priority order per spec §7
	if (chess.isCheckmate()) {
		// Determine winner: the side who just moved (turn is now the loser's turn)
		const winner = chessJsToHookColor(chess.turn() === 'w' ? 'b' : 'w');
		return { kind: 'checkmate', winner };
	}

	if (chess.isStalemate()) {
		return { kind: 'stalemate' };
	}

	if (chess.isInsufficientMaterial()) {
		return { kind: 'draw', reason: 'insufficient-material' };
	}

	if (chess.isThreefoldRepetition()) {
		return { kind: 'draw', reason: 'threefold-repetition' };
	}

	if (chess.isDrawByFiftyMoves()) {
		return { kind: 'draw', reason: 'fifty-move' };
	}

	if (chess.isDraw()) {
		return { kind: 'draw', reason: 'other' };
	}

	return { kind: 'playing' };
}

/** Build formatted move history for agent prompt (e.g. "1. e4 e5 2. Nf3") */
function buildMoveHistory(moves: string[]): string {
	if (moves.length === 0) return '';

	const parts: string[] = [];
	for (let i = 0; i < moves.length; i += 2) {
		const moveNumber = Math.floor(i / 2) + 1;
		const whiteMove = moves[i];
		const blackMove = moves[i + 1];

		if (blackMove) {
			parts.push(`${moveNumber}. ${whiteMove} ${blackMove}`);
		} else {
			parts.push(`${moveNumber}. ${whiteMove}`);
		}
	}

	return parts.join(' ');
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Chess game state management hook.
 *
 * Initializes with either a loaded game (from localStorage) or a fresh game.
 * Manages all game state, move application, and persistence.
 */
export function useChessGame(playerColor: 'white' | 'black'): UseChessGameReturn {
	const [fen, setFen] = useState('');
	const [moves, setMoves] = useState<string[]>([]);
	const [outcome, setOutcome] = useState<GameOutcome>({ kind: 'playing' });
	const [turn, setTurn] = useState<'white' | 'black'>('white');
	const [legalMoves, setLegalMoves] = useState<string[]>([]);

	// Keep refs to the chess instance and current playerColor
	const chessRef = useRef(new Chess());
	const playerColorRef = useRef(playerColor);

	// Update playerColorRef when playerColor prop changes
	useEffect(() => {
		playerColorRef.current = playerColor;
	}, [playerColor]);

	// Initialize on mount: load from localStorage or start fresh
	useEffect(() => {
		const initGame = () => {
			try {
				const saved = localStorage.getItem(LOCALSTORAGE_KEY);
				if (saved) {
					const parsed = JSON.parse(saved);
					const { moves: savedMoves, playerColor: savedPlayerColor } =
						parsed;

					// Only restore if it's the same player color (don't cross-load games)
					if (savedPlayerColor === playerColor && Array.isArray(savedMoves)) {
						// Replay moves through a fresh chess.js instance
						const chess = new Chess();
						try {
							for (const sanMove of savedMoves) {
								chess.move(sanMove);
							}
							chessRef.current = chess;
							setFen(chess.fen());
							setMoves(savedMoves);
							const newOutcome = deriveOutcome(chess);
							setOutcome(newOutcome);
							setTurn(chessJsToHookColor(chess.turn()));
							setLegalMoves(chess.moves());
							return;
						} catch {
							// Replay failed — corrupted data. Clear localStorage and start fresh.
							localStorage.removeItem(LOCALSTORAGE_KEY);
						}
					}
				}
			} catch {
				// localStorage parse error — clear and start fresh
				localStorage.removeItem(LOCALSTORAGE_KEY);
			}

			// Start fresh game
			const chess = new Chess();
			chessRef.current = chess;
			setFen(chess.fen());
			setMoves([]);
			setOutcome({ kind: 'playing' });
			setTurn(chessJsToHookColor(chess.turn()));
			setLegalMoves(chess.moves());
		};

		initGame();
	}, [playerColor]);

	/** Persist current state to localStorage */
	const persistToLocalStorage = useCallback(() => {
		try {
			localStorage.setItem(
				LOCALSTORAGE_KEY,
				JSON.stringify({
					playerColor: playerColorRef.current,
					moves,
					fen: chessRef.current.fen(),
				})
			);
		} catch {
			// localStorage unavailable — silently fail (not fatal to gameplay)
		}
	}, [moves]);

	/** Derive and return new outcome, updating state and localStorage */
	const updateOutcomeAndPersist = useCallback((newMoves: string[]) => {
		const newOutcome = deriveOutcome(chessRef.current);
		setOutcome(newOutcome);
		setTurn(chessJsToHookColor(chessRef.current.turn()));
		setLegalMoves(chessRef.current.moves());
		setMoves(newMoves);

		// Persist immediately after successful move
		try {
			localStorage.setItem(
				LOCALSTORAGE_KEY,
				JSON.stringify({
					playerColor: playerColorRef.current,
					moves: newMoves,
					fen: chessRef.current.fen(),
				})
			);
		} catch {
			// localStorage unavailable — silently fail
		}
	}, []);

	const applyPlayerMove = useCallback(
		(from: string, to: string, promotion?: string): boolean => {
			let moveResult;
			try {
				const moveObj = { from, to };
				const move = promotion
					? { ...moveObj, promotion }
					: moveObj;
				moveResult = chessRef.current.move(move);
			} catch {
				// Move is illegal — return false without changing state
				return false;
			}

			// Move succeeded; get SAN from the returned Move object
			const san = moveResult.san;
			const updatedMoves = [...moves, san];

			updateOutcomeAndPersist(updatedMoves);
			setFen(chessRef.current.fen());
			return true;
		},
		[moves, updateOutcomeAndPersist]
	);

	const needsPromotionChoice = useCallback(
		(from: string, to: string): boolean => {
			try {
				// Get verbose moves from all positions, then filter to those from the source square
				// (chess.js square parameter is type-strict, so we filter instead of casting)
				const verboseMoves = chessRef.current.moves({
					verbose: true,
				}) as Move[];

				// Check if any move to this square requires promotion
				return verboseMoves.some(
					(m) => m.from === from && m.to === to && m.promotion
				);
			} catch {
				return false;
			}
		},
		[]
	);

	const applyAgentMove = useCallback(
		(san: string): boolean => {
			try {
				chessRef.current.move(san);
			} catch {
				// Move is illegal — return false without changing state
				return false;
			}

			// Move succeeded
			const updatedMoves = [...moves, san];
			updateOutcomeAndPersist(updatedMoves);
			setFen(chessRef.current.fen());
			return true;
		},
		[moves, updateOutcomeAndPersist]
	);

	const resign = useCallback(() => {
		setOutcome({ kind: 'resigned', by: 'player' });
		persistToLocalStorage();
	}, [persistToLocalStorage]);

	const newGame = useCallback((newPlayerColor: 'white' | 'black') => {
		playerColorRef.current = newPlayerColor;
		const chess = new Chess();
		chessRef.current = chess;
		setFen(chess.fen());
		setMoves([]);
		setOutcome({ kind: 'playing' });
		setTurn(chessJsToHookColor(chess.turn()));
		setLegalMoves(chess.moves());

		// Clear localStorage for old game
		localStorage.removeItem(LOCALSTORAGE_KEY);
	}, []);

	const history = buildMoveHistory(moves);
	const isPlayerTurn = turn === playerColor && outcome.kind === 'playing';

	return {
		fen,
		moves,
		outcome,
		turn,
		isPlayerTurn,
		legalMoves,
		applyPlayerMove,
		needsPromotionChoice,
		applyAgentMove,
		resign,
		newGame,
		history,
	};
}
