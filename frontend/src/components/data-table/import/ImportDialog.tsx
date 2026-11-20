import type { DataTableSchema } from '@/types/dataTable.types';

export interface ImportDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	schema: DataTableSchema;
	onImported?: () => void;
}

/** Stub; implemented by TB-9. */
export function ImportDialog(_props: ImportDialogProps): null {
	return null;
}
