import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
	Download,
	Upload,
	FileText,
	Loader2,
	CheckCircle2,
	XCircle,
	AlertTriangle,
} from 'lucide-react';
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { file as frappeFile } from '@/lib/frappe-sdk';
import {
	getBulkImportTemplateUrl,
	startTableBulkImport,
	getTableBulkImportStatus,
	type BulkImportStatus,
} from '@/services/dataTableApi';

const TERMINAL_STATUSES = new Set(['Success', 'Partial Success', 'Error', 'Timed Out']);
const POLL_INTERVAL_MS = 2000;

interface BulkImportModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	tableId: string;
	tableName: string;
	onImportComplete?: () => void;
}

export function BulkImportModal({
	open,
	onOpenChange,
	tableId,
	tableName,
	onImportComplete,
}: BulkImportModalProps) {
	const [downloadingTemplate, setDownloadingTemplate] = useState(false);
	const [selectedFile, setSelectedFile] = useState<File | null>(null);
	const [uploadedFileUrl, setUploadedFileUrl] = useState('');
	const [uploading, setUploading] = useState(false);
	const [uploadProgress, setUploadProgress] = useState(0);
	const [dragOver, setDragOver] = useState(false);
	const [importing, setImporting] = useState(false);
	const [importStatus, setImportStatus] = useState<BulkImportStatus | null>(null);

	const fileInputRef = useRef<HTMLInputElement>(null);
	const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

	const stopPolling = useCallback(() => {
		if (pollTimerRef.current) {
			clearTimeout(pollTimerRef.current);
			pollTimerRef.current = null;
		}
	}, []);

	const resetState = useCallback(() => {
		stopPolling();
		setSelectedFile(null);
		setUploadedFileUrl('');
		setUploading(false);
		setUploadProgress(0);
		setDragOver(false);
		setImporting(false);
		setImportStatus(null);
		if (fileInputRef.current) fileInputRef.current.value = '';
	}, [stopPolling]);

	// Reset whenever the modal is closed; stop polling on unmount.
	useEffect(() => {
		if (!open) resetState();
	}, [open, resetState]);

	useEffect(() => stopPolling, [stopPolling]);

	const handleOpenChange = (next: boolean) => {
		// Don't allow closing mid-import poll; the user can cancel after it finishes.
		if (importing && !isTerminal(importStatus)) return;
		onOpenChange(next);
	};

	const isTerminal = (status: BulkImportStatus | null) =>
		status !== null && TERMINAL_STATUSES.has(status.status);

	const handleDownloadTemplate = async () => {
		setDownloadingTemplate(true);
		try {
			const template = await getBulkImportTemplateUrl(tableId);
			const link = document.createElement('a');
			link.href = template.file_url;
			link.download = template.file_name;
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
		} catch (err: any) {
			toast.error('Failed to download template', { description: err.message });
		} finally {
			setDownloadingTemplate(false);
		}
	};

	const uploadSelectedFile = async (fileToUpload: File) => {
		setUploading(true);
		setUploadProgress(0);
		try {
			const response = await frappeFile.uploadFile(
				fileToUpload,
				{ isPrivate: true },
				(completed, total) => {
					if (total) setUploadProgress(Math.round((completed / total) * 100));
				}
			);
			const res = response as any;
			const fileUrl = res?.data?.message?.file_url;
			if (fileUrl) {
				setUploadedFileUrl(fileUrl);
			} else {
				toast.error('Upload succeeded but no file URL returned');
				setSelectedFile(null);
			}
		} catch {
			toast.error('Failed to upload file');
			setSelectedFile(null);
		} finally {
			setUploading(false);
		}
	};

	const acceptFile = (file: File | undefined | null) => {
		if (!file) return;
		if (!file.name.toLowerCase().endsWith('.csv')) {
			toast.error('Only CSV files are supported');
			return;
		}
		setSelectedFile(file);
		setUploadedFileUrl('');
		uploadSelectedFile(file);
	};

	const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
		acceptFile(e.target.files?.[0]);
	};

	const handleDrop = (e: React.DragEvent) => {
		e.preventDefault();
		setDragOver(false);
		if (uploading || importing) return;
		acceptFile(e.dataTransfer.files?.[0]);
	};

	const pollStatus = useCallback(
		async (importName: string) => {
			try {
				const status = await getTableBulkImportStatus(importName);
				setImportStatus(status);
				if (TERMINAL_STATUSES.has(status.status)) {
					setImporting(false);
					if (status.status === 'Success') {
						toast.success(`Import complete: ${status.success} record(s) imported`);
					} else if (status.status === 'Partial Success') {
						toast.warning(
							`Import partially complete: ${status.success} imported, ${status.failed} failed`
						);
					} else {
						toast.error('Import failed', {
							description: `${status.failed} row(s) failed`,
						});
					}
					onImportComplete?.();
					return;
				}
			} catch (err: any) {
				setImporting(false);
				toast.error('Failed to check import status', { description: err.message });
				return;
			}
			pollTimerRef.current = setTimeout(() => pollStatus(importName), POLL_INTERVAL_MS);
		},
		[onImportComplete]
	);

	const handleStartImport = async () => {
		if (!uploadedFileUrl) return;
		setImporting(true);
		setImportStatus(null);
		try {
			const result = await startTableBulkImport(tableId, uploadedFileUrl);
			pollTimerRef.current = setTimeout(
				() => pollStatus(result.import_name),
				POLL_INTERVAL_MS
			);
		} catch (err: any) {
			setImporting(false);
			toast.error('Failed to start import', { description: err.message });
		}
	};

	const renderResult = () => {
		if (!importStatus || !isTerminal(importStatus)) return null;
		const failed = importStatus.failed > 0;
		return (
			<div className="rounded-md border p-3 space-y-2">
				<div className="flex items-center gap-4 text-sm">
					<span className="flex items-center gap-1.5 text-good">
						<CheckCircle2 className="w-4 h-4" />
						{importStatus.success} imported
					</span>
					{failed && (
						<span className="flex items-center gap-1.5 text-destructive">
							<XCircle className="w-4 h-4" />
							{importStatus.failed} failed
						</span>
					)}
					<span className="text-steel-soft text-xs ml-auto">
						{importStatus.total} total
					</span>
				</div>
				{importStatus.errors.length > 0 && (
					<div className="max-h-32 overflow-auto rounded bg-muted/50 p-2 space-y-1">
						{importStatus.errors.map((err, i) => (
							<p key={i} className="text-xs text-destructive font-mono">
								Rows {err.row_indexes}: {err.messages || err.exception}
							</p>
						))}
					</div>
				)}
			</div>
		);
	};

	const importFinished = isTerminal(importStatus);

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogContent className="sm:max-w-md">
				<DialogHeader>
					<DialogTitle>Import data into {tableName}</DialogTitle>
					<DialogDescription>
						Download the CSV template, fill in your data, then upload and import it.
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-4 py-2">
					{/* Step 1: Template */}
					<div className="space-y-1.5">
						<p className="text-sm font-medium">1. Download the template</p>
						<Button
							variant="outline"
							size="sm"
							onClick={handleDownloadTemplate}
							disabled={downloadingTemplate || importing}
						>
							{downloadingTemplate ? (
								<Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
							) : (
								<Download className="w-3.5 h-3.5 mr-1.5" />
							)}
							Download CSV template
						</Button>
					</div>

					{/* Step 2: Upload */}
					<div className="space-y-1.5">
						<p className="text-sm font-medium">2. Upload your CSV file</p>
						<div
							className={`flex flex-col items-center justify-center gap-2 rounded-md border border-dashed p-6 text-center transition-colors ${
								dragOver ? 'border-primary bg-primary/5' : 'border-input'
							} ${uploading || importing ? 'opacity-60 pointer-events-none' : 'cursor-pointer'}`}
							onClick={() => fileInputRef.current?.click()}
							onDragOver={(e) => {
								e.preventDefault();
								if (!uploading && !importing) setDragOver(true);
							}}
							onDragLeave={() => setDragOver(false)}
							onDrop={handleDrop}
						>
							{uploading ? (
								<>
									<Loader2 className="w-6 h-6 animate-spin text-steel-soft" />
									<p className="text-xs text-steel">Uploading... {uploadProgress}%</p>
									<Progress value={uploadProgress} className="w-full h-1.5" />
								</>
							) : selectedFile ? (
								<>
									<FileText className="w-6 h-6 text-steel-soft" />
									<p className="text-sm">{selectedFile.name}</p>
									{uploadedFileUrl ? (
										<p className="text-xs text-good flex items-center gap-1">
											<CheckCircle2 className="w-3.5 h-3.5" />
											Uploaded, ready to import
										</p>
									) : (
										<p className="text-xs text-destructive">Upload failed — pick another file</p>
									)}
								</>
							) : (
								<>
									<Upload className="w-6 h-6 text-steel-soft" />
									<p className="text-sm text-steel">
										Drag &amp; drop a CSV file here, or click to browse
									</p>
								</>
							)}
						</div>
						<input
							ref={fileInputRef}
							type="file"
							accept=".csv"
							className="hidden"
							onChange={handleFileSelect}
						/>
					</div>

					{/* Step 3: Import status */}
					{importing && !importFinished && (
						<div className="flex items-center gap-2 text-sm text-steel">
							<Loader2 className="w-4 h-4 animate-spin" />
							Importing records
							{importStatus
								? ` — ${importStatus.success + importStatus.failed}/${importStatus.total || '?'} processed`
								: '...'}
						</div>
					)}
					{importFinished && importStatus?.status === 'Partial Success' && (
						<p className="flex items-center gap-1.5 text-xs text-warning">
							<AlertTriangle className="w-3.5 h-3.5" />
							Some rows failed to import. Review the errors below.
						</p>
					)}
					{renderResult()}
				</div>

				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						{importFinished ? 'Close' : 'Cancel'}
					</Button>
					<Button
						onClick={handleStartImport}
						disabled={!uploadedFileUrl || uploading || importing}
					>
						{importing && !importFinished ? (
							<Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
						) : null}
						Start import
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
