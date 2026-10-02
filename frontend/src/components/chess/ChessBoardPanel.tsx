import { useState, useCallback } from 'react';
import { Chessboard } from 'react-chessboard';
import type { Square } from 'react-chessboard/dist/chessboard/types';
import { PromotionDialog } from './PromotionDialog';
import { cn } from '@/lib/utils';

interface ChessBoardPanelProps {
	/** Current board position in FEN format */
	fen: string;
	/** Board orientation: 'white' (white on bottom) or 'black' (black on bottom) */
	boardOrientation: 'white' | 'black';
	/** Whether the board is disabled (no dragging allowed) */
	disabled: boolean;
	/**
	 * Called when player attempts a move.
	 * Must return true if move was successful, false if illegal/rejected.
	 */
	onPlayerMove: (from: string, to: string, promotion?: string) => boolean;
	/**
	 * Check if a move from→to requires a promotion choice dialog.
	 * Return true if promotion is needed, false otherwise.
	 */
	needsPromotionChoice: (from: string, to: string) => boolean;
}

/**
 * ChessBoardPanel
 *
 * A react-chessboard wrapper that manages piece dragging, move application, and
 * promotion flow. When a pawn promotion is detected, opens a PromotionDialog to
 * let the user choose which piece to promote to before applying the move.
 *
 * Per DESIGN.md §9: board square colors use react-chessboard's sane defaults;
 * any wrapper container uses 2px radius, hairline borders, no shadows.
 */
export function ChessBoardPanel({
	fen,
	boardOrientation,
	disabled,
	onPlayerMove,
	needsPromotionChoice,
}: ChessBoardPanelProps) {
	// Track pending promotion: { from, to } while waiting for piece selection
	const [pendingPromotion, setPendingPromotion] = useState<{
		from: string;
		to: string;
	} | null>(null);

	/**
	 * Handle piece drop from react-chessboard.
	 *
	 * If promotion is needed for this move:
	 *   1. Store the move as pending
	 *   2. Open the promotion dialog
	 *   3. Return false to snap the piece back (move not yet applied)
	 *
	 * If no promotion needed:
	 *   1. Call onPlayerMove directly
	 *   2. Return its boolean result (true = move accepted, false = illegal)
	 */
	const handlePieceDrop = useCallback(
		(sourceSquare: Square, targetSquare: Square): boolean => {
			// Check if this move requires promotion
			if (needsPromotionChoice(sourceSquare, targetSquare)) {
				// Store the move and open dialog
				setPendingPromotion({ from: sourceSquare, to: targetSquare });
				// Return false to snap piece back; actual move happens after dialog
				return false;
			}

			// No promotion needed — apply move directly and return its result
			return onPlayerMove(sourceSquare, targetSquare);
		},
		[needsPromotionChoice, onPlayerMove]
	);

	/**
	 * Handle promotion piece selection from the PromotionDialog.
	 * Apply the move with the chosen promotion piece.
	 */
	const handlePromotionSelect = useCallback(
		(piece: 'q' | 'r' | 'b' | 'n') => {
			if (!pendingPromotion) return;

			// Apply the move with promotion
			onPlayerMove(pendingPromotion.from, pendingPromotion.to, piece);

			// Clear the pending promotion
			setPendingPromotion(null);
		},
		[pendingPromotion, onPlayerMove]
	);

	/**
	 * Handle promotion dialog cancel.
	 * Just close the dialog; the piece already snapped back via return false.
	 */
	const handlePromotionCancel = useCallback(() => {
		setPendingPromotion(null);
	}, []);

	return (
		<div className={cn('rounded-[2px] border border-[var(--line)] bg-[var(--paper)] overflow-hidden')}>
			<Chessboard
				position={fen}
				onPieceDrop={handlePieceDrop}
				boardOrientation={boardOrientation}
				arePiecesDraggable={!disabled}
			/>

			{/* Promotion piece picker dialog */}
			<PromotionDialog
				open={pendingPromotion !== null}
				color={boardOrientation}
				onSelect={handlePromotionSelect}
				onCancel={handlePromotionCancel}
			/>
		</div>
	);
}
