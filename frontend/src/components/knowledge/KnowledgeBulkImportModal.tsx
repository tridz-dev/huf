import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
	Upload,
	FolderOpen,
	Cloud,
	Server,
	FileText,
	Loader2,
	CheckCircle2,
	XCircle,
} from 'lucide-react';
import {
	Dialog,
	DialogDescription,
	DialogTitle,
} from '@/components/ui/dialog';
import {
	DialogScrollBody,
	DialogScrollContent,
	DialogScrollFooter,
	DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { file as frappeFile } from '@/lib/frappe-sdk';
import { db } from '@/lib/frappe-sdk';
import {
	startUploadImport,
	startDirectoryImport,
	startS3Import,
	startSftpImport,
	getJobProgress,
	type IngestionJobProgress,
} from '../../services/bulkIngestionApi';

const TERMINAL_STATUSES = new Set(['Completed', 'Completed with Errors', 'Failed']);
const POLL_INTERVAL_MS = 2000;

type SourceKind = 'Upload' | 'Directory' | 'S3' | 'SFTP';

interface SourceKindOption {
	value: SourceKind;
	label: string;
	icon: typeof Upload;
}

const SOURCE_KIND_OPTIONS: SourceKindOption[] = [
	{ value: 'Upload', label: 'Upload', icon: Upload },
	{ value: 'Directory', label: 'Directory', icon: FolderOpen },
	{ value: 'S3', label: 'S3', icon: Cloud },
	{ value: 'SFTP', label: 'SFTP', icon: Server },
];

interface SSHConnectionOption {
	value: string;
	label: string;
	description?: string;
}

interface KnowledgeBulkImportModalProps {
	knowledgeSource: string;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function KnowledgeBulkImportModal({
	knowledgeSource,
	open,
	onOpenChange,
}: KnowledgeBulkImportModalProps) {
	const [sourceKind, setSourceKind] = useState<SourceKind>('Upload');

	// Upload step state
	const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
	const [uploadedFileUrls, setUploadedFileUrls] = useState<string[]>([]);
	const [uploading, setUploading] = useState(false);
	const [uploadProgress, setUploadProgress] = useState(0);
	const [dragOver, setDragOver] = useState(false);

	// Directory step state
	const [directoryPath, setDirectoryPath] = useState('');

	// S3 step state
	const [s3Bucket, setS3Bucket] = useState('');
	const [s3Prefix, setS3Prefix] = useState('');

	// SFTP step state
	const [sshConnections, setSSHConnections] = useState<SSHConnectionOption[]>([]);
	const [loadingSSHConnections, setLoadingSSHConnections] = useState(false);
	const [sshConnection, setSSHConnection] = useState('');
	const [sftpRootPath, setSftpRootPath] = useState('');

	// Job / progress state
	const [starting, setStarting] = useState(false);
	const [jobName, setJobName] = useState<string | null>(null);
	const [jobProgress, setJobProgress] = useState<IngestionJobProgress | null>(null);

	const fileInputRef = useRef<HTMLInputElement>(null);
	const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

	const stopPolling = useCallback(() => {
		if (pollTimerRef.current) {
			clearTimeout(pollTimerRef.current);
			pollTimerRef.current = null;
		}
	}, []);

	const isTerminal = (progress: IngestionJobProgress | null) =>
		progress !== null && TERMINAL_STATUSES.has(progress.status);

	const resetState = useCallback(() => {
		stopPolling();
		setSourceKind('Upload');
		setSelectedFiles([]);
		setUploadedFileUrls([]);
		setUploading(false);
		setUploadProgress(0);
		setDragOver(false);
		setDirectoryPath('');
		setS3Bucket('');
		setS3Prefix('');
		setSSHConnection('');
		setSftpRootPath('');
		setStarting(false);
		setJobName(null);
		setJobProgress(null);
		if (fileInputRef.current) fileInputRef.current.value = '';
	}, [stopPolling]);

	// Reset whenever the modal is closed; stop polling on unmount.
	useEffect(() => {
		if (!open) resetState();
	}, [open, resetState]);

	useEffect(() => stopPolling, [stopPolling]);

	// Load SSH Connection options when the SFTP step is selected, mirroring
	// KnowledgeSourceFormPage's Link-field option fetching approach.
	useEffect(() => {
		if (!open || sourceKind !== 'SFTP') return;
		let cancelled = false;

		const loadSSHConnections = async () => {
			setLoadingSSHConnections(true);
			try {
				const rows = (await db.getDocList('SSH Connection', {
					fields: ['name', 'display_name', 'host', 'username'],
					filters: [['enabled', '=', 1]],
					limit: 500,
					orderBy: { field: 'modified', order: 'desc' },
				})) as Array<{
					name: string;
					display_name?: string | null;
					host?: string | null;
					username?: string | null;
				}>;
				if (cancelled) return;
				setSSHConnections(
					rows.map((row) => ({
						value: row.name,
						label: row.display_name || row.name,
						description: [row.username, row.host].filter(Boolean).join('@') || undefined,
					}))
				);
			} catch {
				if (!cancelled) {
					setSSHConnections([]);
					toast.error('Failed to load SSH Connections');
				}
			} finally {
				if (!cancelled) setLoadingSSHConnections(false);
			}
		};

		loadSSHConnections();
		return () => {
			cancelled = true;
		};
	}, [open, sourceKind]);

	const handleOpenChange = (next: boolean) => {
		// Don't allow closing mid-import poll; the user can close after it finishes.
		if (jobName && !isTerminal(jobProgress)) return;
		onOpenChange(next);
	};

	const uploadSelectedFiles = async (files: File[]) => {
		setUploading(true);
		setUploadProgress(0);
		const urls: string[] = [];
		try {
			for (let i = 0; i < files.length; i++) {
				const response = await frappeFile.uploadFile(
					files[i],
					{ isPrivate: true },
					(completed, total) => {
						if (total) {
							const fileFraction = completed / total;
							setUploadProgress(Math.round(((i + fileFraction) / files.length) * 100));
						}
					}
				);
				const res = response as any;
				const fileUrl = res?.data?.message?.file_url;
				if (fileUrl) urls.push(fileUrl);
			}
			if (urls.length === 0) {
				toast.error('Upload succeeded but no file URLs returned');
				setSelectedFiles([]);
			} else {
				setUploadedFileUrls(urls);
				if (urls.length < files.length) {
					toast.warning(`Only ${urls.length} of ${files.length} file(s) uploaded successfully`);
				}
			}
		} catch {
			toast.error('Failed to upload file(s)');
			setSelectedFiles([]);
		} finally {
			setUploading(false);
		}
	};

	const acceptFiles = (files: FileList | File[] | undefined | null) => {
		if (!files || files.length === 0) return;
		const fileArray = Array.from(files);
		setSelectedFiles(fileArray);
		setUploadedFileUrls([]);
		uploadSelectedFiles(fileArray);
	};

	const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
		acceptFiles(e.target.files);
	};

	const handleDrop = (e: React.DragEvent) => {
		e.preventDefault();
		setDragOver(false);
		if (uploading || starting || jobName) return;
		acceptFiles(e.dataTransfer.files);
	};

	const pollProgress = useCallback(async (name: string) => {
		try {
			const progress = await getJobProgress(name);
			setJobProgress(progress);
			if (TERMINAL_STATUSES.has(progress.status)) {
				if (progress.status === 'Completed') {
					toast.success(`Import complete: ${progress.succeeded} item(s) imported`);
				} else if (progress.status === 'Completed with Errors') {
					toast.warning(
						`Import completed with errors: ${progress.succeeded} succeeded, ${progress.failed} failed`
					);
				} else {
					toast.error('Import failed', { description: `${progress.failed} item(s) failed` });
				}
				return;
			}
		} catch (err: any) {
			toast.error('Failed to check import progress', { description: err.message });
			return;
		}
		pollTimerRef.current = setTimeout(() => pollProgress(name), POLL_INTERVAL_MS);
	}, []);

	const beginPolling = (name: string) => {
		setJobName(name);
		setJobProgress(null);
		pollTimerRef.current = setTimeout(() => pollProgress(name), POLL_INTERVAL_MS);
	};

	const canStart = (() => {
		switch (sourceKind) {
			case 'Upload':
				return uploadedFileUrls.length > 0 && !uploading;
			case 'Directory':
				return directoryPath.trim().length > 0;
			case 'S3':
				return s3Bucket.trim().length > 0;
			case 'SFTP':
				return sshConnection.length > 0 && sftpRootPath.trim().length > 0;
			default:
				return false;
		}
	})();

	const handleStartImport = async () => {
		if (!canStart) return;
		setStarting(true);
		try {
			let result: { ingestion_job: string };
			switch (sourceKind) {
				case 'Upload':
					result = await startUploadImport(knowledgeSource, uploadedFileUrls);
					break;
				case 'Directory':
					result = await startDirectoryImport(knowledgeSource, directoryPath.trim());
					break;
				case 'S3':
					result = await startS3Import(knowledgeSource, s3Bucket.trim(), s3Prefix.trim() || undefined);
					break;
				case 'SFTP':
					result = await startSftpImport(knowledgeSource, sshConnection, sftpRootPath.trim());
					break;
			}
			beginPolling(result.ingestion_job);
		} catch (err: any) {
			toast.error('Failed to start import', { description: err.message });
		} finally {
			setStarting(false);
		}
	};

	const jobFinished = isTerminal(jobProgress);
	const showProgressView = jobName !== null;

	const renderSourceKindPicker = () => (
		<div className="grid grid-cols-4 gap-2">
			{SOURCE_KIND_OPTIONS.map(({ value, label, icon: Icon }) => (
				<button
					key={value}
					type="button"
					onClick={() => setSourceKind(value)}
					className={`flex flex-col items-center justify-center gap-1.5 rounded-none border p-3 text-xs transition-colors ${
						sourceKind === value
							? 'border-primary bg-primary/5 text-foreground'
							: 'border-input text-steel hover:bg-muted/40'
					}`}
				>
					<Icon className="w-4 h-4" />
					{label}
				</button>
			))}
		</div>
	);

	const renderUploadStep = () => (
		<div className="space-y-1.5">
			<div
				className={`flex flex-col items-center justify-center gap-2 rounded-md border border-dashed p-6 text-center transition-colors ${
					dragOver ? 'border-primary bg-primary/5' : 'border-input'
				} ${uploading ? 'opacity-60 pointer-events-none' : 'cursor-pointer'}`}
				onClick={() => fileInputRef.current?.click()}
				onDragOver={(e) => {
					e.preventDefault();
					if (!uploading) setDragOver(true);
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
				) : selectedFiles.length > 0 ? (
					<>
						<FileText className="w-6 h-6 text-steel-soft" />
						<p className="text-sm">
							{selectedFiles.length} file{selectedFiles.length === 1 ? '' : 's'} selected
						</p>
						{uploadedFileUrls.length > 0 ? (
							<p className="text-xs text-green-600 flex items-center gap-1">
								<CheckCircle2 className="w-3.5 h-3.5" />
								{uploadedFileUrls.length} uploaded, ready to import
							</p>
						) : (
							<p className="text-xs text-destructive">Upload failed — pick another file</p>
						)}
					</>
				) : (
					<>
						<Upload className="w-6 h-6 text-steel-soft" />
						<p className="text-sm text-steel">
							Drag &amp; drop files or a .zip archive here, or click to browse
						</p>
					</>
				)}
			</div>
			<input
				ref={fileInputRef}
				type="file"
				multiple
				accept=".zip,*"
				className="hidden"
				onChange={handleFileSelect}
			/>
		</div>
	);

	const renderDirectoryStep = () => (
		<div className="space-y-1.5">
			<Label htmlFor="bulk-import-directory">Server path</Label>
			<Input
				id="bulk-import-directory"
				placeholder="/data/shared/docs"
				value={directoryPath}
				onChange={(e) => setDirectoryPath(e.target.value)}
			/>
			<p className="text-xs text-steel-soft">
				This is an absolute path on the server filesystem. Admin use only.
			</p>
		</div>
	);

	const renderS3Step = () => (
		<div className="space-y-3">
			<div className="space-y-1.5">
				<Label htmlFor="bulk-import-s3-bucket">Bucket name</Label>
				<Input
					id="bulk-import-s3-bucket"
					placeholder="my-bucket"
					value={s3Bucket}
					onChange={(e) => setS3Bucket(e.target.value)}
				/>
			</div>
			<div className="space-y-1.5">
				<Label htmlFor="bulk-import-s3-prefix">Prefix (optional)</Label>
				<Input
					id="bulk-import-s3-prefix"
					placeholder="docs/2024/"
					value={s3Prefix}
					onChange={(e) => setS3Prefix(e.target.value)}
				/>
			</div>
		</div>
	);

	const renderSftpStep = () => (
		<div className="space-y-3">
			<div className="space-y-1.5">
				<Label>SSH Connection</Label>
				<Select value={sshConnection} onValueChange={setSSHConnection}>
					<SelectTrigger>
						<SelectValue
							placeholder={loadingSSHConnections ? 'Loading connections...' : 'Select a connection'}
						/>
					</SelectTrigger>
					<SelectContent>
						{sshConnections.map((conn) => (
							<SelectItem key={conn.value} value={conn.value}>
								{conn.label}
								{conn.description ? ` (${conn.description})` : ''}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</div>
			<div className="space-y-1.5">
				<Label htmlFor="bulk-import-sftp-path">Root path to scan</Label>
				<Input
					id="bulk-import-sftp-path"
					placeholder="/home/user/docs"
					value={sftpRootPath}
					onChange={(e) => setSftpRootPath(e.target.value)}
				/>
			</div>
		</div>
	);

	const renderSourceStep = () => {
		switch (sourceKind) {
			case 'Upload':
				return renderUploadStep();
			case 'Directory':
				return renderDirectoryStep();
			case 'S3':
				return renderS3Step();
			case 'SFTP':
				return renderSftpStep();
			default:
				return null;
		}
	};

	const renderProgressView = () => {
		const totalDiscovered = jobProgress?.total_discovered ?? 0;
		const processed = jobProgress
			? jobProgress.succeeded + jobProgress.failed + jobProgress.skipped
			: 0;
		const progressValue = totalDiscovered > 0 ? Math.round((processed / totalDiscovered) * 100) : 0;
		const failedItems = jobProgress?.items?.filter((item) => item.status === 'Failed') ?? [];

		return (
			<div className="space-y-4">
				<div className="flex items-center gap-2 text-sm text-steel">
					{!jobFinished && <Loader2 className="w-4 h-4 animate-spin" />}
					{jobProgress?.status || 'Starting...'}
				</div>

				<div className="space-y-1.5">
					<Progress value={progressValue} className="w-full h-1.5" />
					<p className="text-xs text-steel-soft">
						{processed} / {totalDiscovered || '?'} processed
					</p>
				</div>

				<div className="grid grid-cols-4 gap-2 text-center text-xs">
					<div className="rounded-none border p-2">
						<p className="text-green-600 font-medium">{jobProgress?.succeeded ?? 0}</p>
						<p className="text-steel-soft">Succeeded</p>
					</div>
					<div className="rounded-none border p-2">
						<p className="text-destructive font-medium">{jobProgress?.failed ?? 0}</p>
						<p className="text-steel-soft">Failed</p>
					</div>
					<div className="rounded-none border p-2">
						<p className="text-amber-600 font-medium">{jobProgress?.skipped ?? 0}</p>
						<p className="text-steel-soft">Skipped</p>
					</div>
					<div className="rounded-none border p-2">
						<p className="font-medium">
							{Math.max(totalDiscovered - processed, 0)}
						</p>
						<p className="text-steel-soft">Pending</p>
					</div>
				</div>

				{failedItems.length > 0 && (
					<div className="space-y-1.5">
						<p className="text-sm font-medium flex items-center gap-1.5">
							<XCircle className="w-3.5 h-3.5 text-destructive" />
							Failed items
						</p>
						<div className="max-h-40 overflow-auto rounded bg-muted/50 p-2 space-y-1.5">
							{failedItems.map((item, i) => (
								<div key={i} className="text-xs font-mono">
									<p className="text-foreground truncate">{item.external_path}</p>
									<p className="text-destructive">{item.error_message}</p>
								</div>
							))}
						</div>
					</div>
				)}
			</div>
		);
	};

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogScrollContent className="max-w-lg">
				<DialogScrollHeader>
					<DialogTitle>Bulk Import</DialogTitle>
					<DialogDescription>
						Import many documents into this knowledge source at once.
					</DialogDescription>
				</DialogScrollHeader>

				<DialogScrollBody className="space-y-4 py-2">
					{showProgressView ? (
						renderProgressView()
					) : (
						<>
							<div className="space-y-1.5">
								<p className="text-sm font-medium">1. Choose a source</p>
								{renderSourceKindPicker()}
							</div>
							<div className="space-y-1.5">
								<p className="text-sm font-medium">2. Configure</p>
								{renderSourceStep()}
							</div>
						</>
					)}
				</DialogScrollBody>

				<DialogScrollFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						{jobFinished || !showProgressView ? 'Close' : 'Cancel'}
					</Button>
					{!showProgressView && (
						<Button onClick={handleStartImport} disabled={!canStart || starting}>
							{starting && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
							Start Import
						</Button>
					)}
				</DialogScrollFooter>
			</DialogScrollContent>
		</Dialog>
	);
}
