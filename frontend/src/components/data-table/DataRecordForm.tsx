import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
	SheetFooter,
} from '@/components/ui/sheet';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { createTableRecord, updateTableRecord } from '@/services/dataTableApi';
import type { DataTableFieldDef } from '@/types/dataTable.types';
import { FieldInput, initFormData } from './DataRecordFormLayout';
import { buildFormLayout, type LayoutSection } from '@/utils/dataTableLayout';

interface DataRecordFormProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	doctypeName: string;
	fields: DataTableFieldDef[];
	record?: Record<string, unknown> | null;
	onSaved: () => void;
}

export function DataRecordForm({
	open,
	onOpenChange,
	doctypeName,
	fields,
	record,
	onSaved,
}: DataRecordFormProps) {
	const isEdit = !!record;
	const [formData, setFormData] = useState<Record<string, unknown>>(() =>
		initFormData(fields, record)
	);
	const [saving, setSaving] = useState(false);

	useEffect(() => {
		if (open) {
			setFormData(initFormData(fields, record));
		}
	}, [open, record, fields]);

	const handleOpen = (isOpen: boolean) => {
		onOpenChange(isOpen);
	};

	const setValue = (fieldname: string, value: unknown) => {
		setFormData((prev) => ({ ...prev, [fieldname]: value }));
	};

	const handleSave = async () => {
		setSaving(true);
		try {
			if (isEdit && record?.name) {
				await updateTableRecord(doctypeName, record.name as string, formData);
				toast.success('Record updated');
			} else {
				await createTableRecord(doctypeName, formData);
				toast.success('Record created');
			}
			onSaved();
			onOpenChange(false);
		} catch (err) {
			toast.error(isEdit ? 'Failed to update record' : 'Failed to create record', {
				description: err instanceof Error ? err.message : undefined,
			});
		} finally {
			setSaving(false);
		}
	};

	const dataFields = fields.filter(
		(field) => field.fieldtype !== 'Tab Break' && field.fieldtype !== 'Section Break' && field.fieldtype !== 'Column Break'
	);
	const layout = buildFormLayout(fields);
	const hasTabs = layout.tabs.length > 1;

	const renderSection = (section: LayoutSection, sIdx: number) => (
		<div key={sIdx}>
			{sIdx > 0 && <Separator className="my-4" />}
			{section.label && (
				<p className="text-sm font-medium text-muted-foreground mb-3">
					{section.label}
				</p>
			)}
			{section.columns.length > 1 ? (
				<div
					className="grid gap-4"
					style={{ gridTemplateColumns: `repeat(${section.columns.length}, minmax(0, 1fr))` }}
				>
					{section.columns.map((col, cIdx) => (
						<div key={cIdx} className="space-y-4">
							{col.fields.map((field) => (
								<FieldInput
									key={field.fieldname}
									field={field}
									value={formData[field.fieldname]}
									onChange={(val) => setValue(field.fieldname, val)}
								/>
							))}
						</div>
					))}
				</div>
			) : (
				<div className="space-y-4">
					{section.columns[0]?.fields.map((field) => (
						<FieldInput
							key={field.fieldname}
							field={field}
							value={formData[field.fieldname]}
							onChange={(val) => setValue(field.fieldname, val)}
						/>
					))}
				</div>
			)}
		</div>
	);

	return (
		<Sheet open={open} onOpenChange={handleOpen}>
			<SheetContent className="overflow-y-auto sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>{isEdit ? 'Edit Record' : 'Add New Record'}</SheetTitle>
				</SheetHeader>
				<div className="space-y-4 py-4">
					{hasTabs ? (
						<Tabs defaultValue="tab-0" className="w-full">
							<TabsList className="w-full justify-start rounded-none border-b border-line bg-transparent p-0">
								{layout.tabs.map((tab, tIdx) => (
									<TabsTrigger
										key={`tab-${tIdx}`}
										value={`tab-${tIdx}`}
										className="rounded-none border-b-2 border-transparent px-4 py-2 font-medium text-steel-soft hover:bg-paper-deep hover:text-ink data-[state=active]:border-ink data-[state=active]:text-ink data-[state=active]:bg-transparent data-[state=active]:shadow-none"
									>
										{tab.label || `Tab ${tIdx + 1}`}
									</TabsTrigger>
								))}
							</TabsList>
							{layout.tabs.map((tab, tIdx) => (
								<TabsContent key={`tab-${tIdx}`} value={`tab-${tIdx}`} className="mt-4 focus-visible:outline-none">
									{tab.sections.map((section, sIdx) => renderSection(section, sIdx))}
								</TabsContent>
							))}
						</Tabs>
					) : (
						layout.tabs[0]?.sections.map((section, sIdx) => renderSection(section, sIdx))
					)}

					{dataFields.length === 0 && (
						<p className="text-sm text-muted-foreground text-center py-8">
							No fields defined
						</p>
					)}
				</div>
				<SheetFooter className="gap-2 pt-4">
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						Cancel
					</Button>
					<Button onClick={handleSave} disabled={saving}>
						{saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
						{isEdit ? 'Save Changes' : 'Create Record'}
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}
