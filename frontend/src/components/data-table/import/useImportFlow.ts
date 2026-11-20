import { useCallback, useEffect, useRef, useState } from 'react';
import { file as frappeFile } from '@/lib/frappe-sdk';
import {
	getImportJobStatus,
	getTableBulkImportStatus,
	isQueuedImport,
	previewImport,
	runImport,
	startTableBulkImport,
} from '@/services/dataTableApi';
import type {
	ImportMode,
	ImportPreview,
	RunImportResult,
} from '@/types/dataTable.types';

export const POLL_INTERVAL_MS = 2000;
const LEGACY_TERMINAL = new Set(['Success', 'Partial Success', 'Error', 'Timed Out']);

export type ImportPhase = 'pick' | 'uploading' | 'reviewing' | 'running' | 'done' | 'unsupported' | 'error';

export interface ImportFlow {
	phase: ImportPhase;
	error: string;
	preview: ImportPreview | null;
	mapping: Record<string, string | null>;
	mode: ImportMode;
	keyField: string;
	confirmReplace: boolean;
	progress: number;
	result: RunImportResult | null;
	setMode: (m: ImportMode) => void;
	setKeyField: (k: string) => void;
	setConfirmReplace: (v: boolean) => void;
	map: (header: string, target: string | null) => void;
	chooseFile: (f: File) => Promise<void>;
	startSheet: (url: string) => Promise<void>;
	submit: () => Promise<void>;
	reset: () => void;
}

const isMissingEndpoint = (e: unknown) =>
	/not found|not whitelisted|attributeerror|404|does not exist|no module/i.test(String((e as Error)?.message ?? e));

export function useImportFlow(tableId: string, onImported?: (r: RunImportResult) => void): ImportFlow {
	const [phase, setPhase] = useState<ImportPhase>('pick');
	const [error, setError] = useState('');
	const [fileUrl, setFileUrl] = useState('');
	const [preview, setPreview] = useState<ImportPreview | null>(null);
	const [mapping, setMapping] = useState<Record<string, string | null>>({});
	const [mode, setMode] = useState<ImportMode>('insert');
	const [keyField, setKeyField] = useState('');
	const [confirmReplace, setConfirmReplace] = useState(false);
	const [progress, setProgress] = useState(0);
	const [result, setResult] = useState<RunImportResult | null>(null);
	const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

	const stop = useCallback(() => {
		if (timer.current) clearTimeout(timer.current);
		timer.current = null;
	}, []);
	useEffect(() => stop, [stop]);

	const fail = (e: unknown) => {
		setError(String((e as Error)?.message ?? e));
		setPhase('error');
	};

	const finish = useCallback(
		(r: RunImportResult) => {
			setResult(r);
			setPhase('done');
			onImported?.(r);
		},
		[onImported]
	);

	const reset = useCallback(() => {
		stop();
		setPhase('pick');
		setError('');
		setFileUrl('');
		setPreview(null);
		setMapping({});
		setMode('insert');
		setKeyField('');
		setConfirmReplace(false);
		setProgress(0);
		setResult(null);
	}, [stop]);

	const chooseFile = useCallback(
		async (f: File) => {
			setPhase('uploading');
			try {
				const res = (await frappeFile.uploadFile(f, { isPrivate: true })) as any;
				const url = res?.data?.message?.file_url as string | undefined;
				if (!url) throw new Error('Upload succeeded but no file URL returned');
				setFileUrl(url);
				const p = await previewImport(tableId, url);
				setPreview(p);
				setMapping(Object.fromEntries(p.columns.map((c) => [c.header, c.mapped_field])));
				setPhase('reviewing');
			} catch (e) {
				if (isMissingEndpoint(e)) setPhase('unsupported');
				else fail(e);
			}
		},
		[tableId]
	);

	const pollJob = useCallback(
		(jobId: string) => {
			timer.current = setTimeout(async () => {
				try {
					const s = await getImportJobStatus(jobId);
					setProgress(s.progress ?? 0);
					if (s.status === 'done' && s.result) return finish(s.result);
					if (s.status === 'failed') return fail(s.error ?? 'Import failed');
					pollJob(jobId);
				} catch (e) {
					fail(e);
				}
			}, POLL_INTERVAL_MS);
		},
		[finish]
	);

	const submit = useCallback(async () => {
		setPhase('running');
		try {
			const r = await runImport(tableId, fileUrl, {
				mapping,
				mode,
				keyField: mode === 'update' ? keyField : undefined,
				confirmReplace: mode === 'replace' ? confirmReplace : undefined,
			});
			if (isQueuedImport(r)) pollJob(r.job_id);
			else finish(r);
		} catch (e) {
			fail(e);
		}
	}, [tableId, fileUrl, mapping, mode, keyField, confirmReplace, pollJob, finish]);

	// Legacy Google Sheet path: Data Import job, polled until terminal.
	const startSheet = useCallback(
		async (url: string) => {
			setPhase('running');
			try {
				const { import_name } = await startTableBulkImport(tableId, url);
				const tick = () => {
					timer.current = setTimeout(async () => {
						try {
							const s = await getTableBulkImportStatus(import_name);
							if (LEGACY_TERMINAL.has(s.status)) {
								return finish({
									inserted: s.success,
									updated: 0,
									rejected: s.failed,
									rejected_rows: [],
									rejected_csv: '',
								});
							}
							if (s.total) setProgress(Math.round(((s.success + s.failed) / s.total) * 100));
							tick();
						} catch (e) {
							fail(e);
						}
					}, POLL_INTERVAL_MS);
				};
				tick();
			} catch (e) {
				fail(e);
			}
		},
		[tableId, finish]
	);

	return {
		phase, error, preview, mapping, mode, keyField, confirmReplace, progress, result,
		setMode, setKeyField, setConfirmReplace, startSheet, chooseFile, submit, reset,
		map: (header, target) => setMapping((m) => ({ ...m, [header]: target })),
	};
}
