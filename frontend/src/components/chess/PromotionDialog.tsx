import React from 'react';
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog';
import { ChessQueen, ChessRook, ChessBishop, ChessKnight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PromotionDialogProps {
	/** Whether the dialog is open */
	open: boolean;
	/** Piece color: white or black (reserved for future piece variant styling) */
	color: 'white' | 'black';
	/** Called when a piece is selected, with the piece code ('q', 'r', 'b', 'n') */
	onSelect: (piece: 'q' | 'r' | 'b' | 'n') => void;
	/** Called when the user cancels the dialog */
	onCancel: () => void;
}

/**
 * PromotionDialog
 *
 * A Radix Dialog showing four promotable chess pieces (Queen, Rook, Bishop, Knight).
 * The user clicks one to complete a pawn promotion. Per DESIGN.md §9: outline-only
 * icons, `--steel` default → `--ink` on hover, no colored fills, 2px radius, hairline
 * borders, no shadows.
 */
export function PromotionDialog({
	open,
	color,
	onSelect,
	onCancel,
}: PromotionDialogProps) {
	const pieces: Array<{
		code: 'q' | 'r' | 'b' | 'n';
		label: string;
		icon: React.ReactNode;
	}> = [
		{
			code: 'q',
			label: 'Queen',
			icon: <ChessQueen className="w-8 h-8" strokeWidth={1.5} />,
		},
		{
			code: 'r',
			label: 'Rook',
			icon: <ChessRook className="w-8 h-8" strokeWidth={1.5} />,
		},
		{
			code: 'b',
			label: 'Bishop',
			icon: <ChessBishop className="w-8 h-8" strokeWidth={1.5} />,
		},
		{
			code: 'n',
			label: 'Knight',
			icon: <ChessKnight className="w-8 h-8" strokeWidth={1.5} />,
		},
	];

	const handlePieceClick = (code: 'q' | 'r' | 'b' | 'n') => {
		onSelect(code);
	};

	return (
		<Dialog open={open} onOpenChange={(isOpen) => !isOpen && onCancel()}>
			<DialogContent
				className="w-fit max-w-none rounded-[2px] border border-[var(--line)] bg-[var(--paper)] shadow-none p-0"
				data-piece-color={color}
			>
				<DialogHeader className="px-6 pt-6 pb-4">
					<DialogTitle className="text-sm font-semibold text-[var(--ink)] font-sans">
						Choose promotion piece
					</DialogTitle>
					<DialogDescription className="text-xs text-[var(--steel)] font-sans">
						Select which piece to promote your pawn to
					</DialogDescription>
				</DialogHeader>

				{/* Piece selection grid */}
				<div className="grid grid-cols-4 gap-[1px] px-6 pb-6 bg-[var(--line)]">
					{pieces.map((piece) => (
						<button
							key={piece.code}
							onClick={() => handlePieceClick(piece.code)}
							className={cn(
								'flex flex-col items-center justify-center gap-2 py-4 px-3 bg-[var(--paper)] rounded-[2px] border border-[var(--line)]',
								'text-[var(--steel)] hover:text-[var(--ink)] transition-colors',
								'hover:bg-[var(--paper-deep)] focus:outline-none focus:ring-2 focus:ring-[var(--signal)] focus:ring-offset-2'
							)}
							type="button"
							aria-label={`Promote to ${piece.label}`}
						>
							<div className="text-[var(--steel)] hover:text-[var(--ink)] transition-colors">
								{piece.icon}
							</div>
							<span className="text-[10px] font-medium uppercase font-mono text-[var(--steel)] hover:text-[var(--ink)] transition-colors">
								{piece.label.slice(0, 1)}
							</span>
						</button>
					))}
				</div>
			</DialogContent>
		</Dialog>
	);
}
