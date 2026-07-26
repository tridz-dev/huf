import { useState } from 'react';
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface DeleteTableDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	tableName: string;
	recordCount: number;
	onConfirm: () => void;
	loading?: boolean;
}

export function DeleteTableDialog({
	open,
	onOpenChange,
	tableName,
	recordCount,
	onConfirm,
	loading,
}: DeleteTableDialogProps) {
	const [confirmText, setConfirmText] = useState('');
	const requireConfirmation = recordCount > 0;
	const canDelete = !requireConfirmation || confirmText === tableName;

	return (
		<AlertDialog open={open} onOpenChange={onOpenChange}>
			<AlertDialogContent>
				<AlertDialogHeader>
					<AlertDialogTitle>Delete Table "{tableName}"?</AlertDialogTitle>
					<AlertDialogDescription>
						This will permanently delete the table and all its data.
						{recordCount > 0 && (
							<span className="block mt-2 font-medium text-destructive">
								This table contains {recordCount} record{recordCount !== 1 ? 's' : ''}{' '}
								that will be permanently lost.
							</span>
						)}
					</AlertDialogDescription>
				</AlertDialogHeader>
				{requireConfirmation && (
					<div className="space-y-2 py-2">
						<Label htmlFor="confirm-delete" className="text-sm">
							Type <span className="font-mono font-medium">{tableName}</span> to
							confirm:
						</Label>
						<Input
							id="confirm-delete"
							value={confirmText}
							onChange={(e) => setConfirmText(e.target.value)}
							placeholder={tableName}
							className="h-8"
						/>
					</div>
				)}
				<AlertDialogFooter>
					<AlertDialogCancel onClick={() => setConfirmText('')}>Cancel</AlertDialogCancel>
					<AlertDialogAction
						onClick={() => {
							setConfirmText('');
							onConfirm();
						}}
						disabled={!canDelete || loading}
						className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
					>
						{loading ? 'Deleting...' : 'Delete Table'}
					</AlertDialogAction>
				</AlertDialogFooter>
			</AlertDialogContent>
		</AlertDialog>
	);
}
