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
import { useRef } from 'react';
import type { Blocker } from 'react-router-dom';

interface UnsavedChangesDialogProps {
	blocker: Blocker;
}

export function UnsavedChangesDialog({ blocker }: UnsavedChangesDialogProps) {
	// After proceed(), Radix closes the dialog; resetting then would undo the pending POP navigation.
	const proceededRef = useRef(false);
	return (
		<AlertDialog
			open={blocker.state === 'blocked'}
			onOpenChange={(open) => {
				if (open) return;
				if (proceededRef.current) { proceededRef.current = false; return; }
				blocker.reset?.();
			}}
		>
			<AlertDialogContent>
				<AlertDialogHeader>
					<AlertDialogTitle>Unsaved changes</AlertDialogTitle>
					<AlertDialogDescription>
						You have unsaved changes. Leave without saving?
					</AlertDialogDescription>
				</AlertDialogHeader>
				<AlertDialogFooter>
					<AlertDialogCancel onClick={() => blocker.reset?.()}>Cancel</AlertDialogCancel>
					<AlertDialogAction onClick={() => { proceededRef.current = true; blocker.proceed?.(); }}>Leave</AlertDialogAction>
				</AlertDialogFooter>
			</AlertDialogContent>
		</AlertDialog>
	);
}
