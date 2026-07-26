import type { DataTableFieldDef } from '@/types/dataTable.types';

export interface LayoutColumn {
	fields: DataTableFieldDef[];
}

export interface LayoutSection {
	label?: string;
	columns: LayoutColumn[];
}

export interface LayoutTab {
	label?: string;
	sections: LayoutSection[];
}

export interface FormLayout {
	tabs: LayoutTab[];
}

const LAYOUT_DEFAULT_LABELS = new Set(['tab break', 'section break', 'column break']);

export function buildFormLayout(fields: DataTableFieldDef[]): FormLayout {
	const layout: FormLayout = {
		tabs: [
			{
				sections: [
					{
						columns: [{ fields: [] }],
					},
				],
			},
		],
	};

	for (const field of fields) {
		const raw = field.label?.trim();
		const label = raw && !LAYOUT_DEFAULT_LABELS.has(raw.toLowerCase()) ? raw : undefined;

		if (field.fieldtype === 'Tab Break') {
			layout.tabs.push({
				label,
				sections: [
					{
						columns: [{ fields: [] }],
					},
				],
			});
		} else if (field.fieldtype === 'Section Break') {
			const currentTab = layout.tabs[layout.tabs.length - 1];
			currentTab.sections.push({
				label,
				columns: [{ fields: [] }],
			});
		} else if (field.fieldtype === 'Column Break') {
			const currentTab = layout.tabs[layout.tabs.length - 1];
			const currentSection = currentTab.sections[currentTab.sections.length - 1];
			currentSection.columns.push({ fields: [] });
		} else {
			const currentTab = layout.tabs[layout.tabs.length - 1];
			const currentSection = currentTab.sections[currentTab.sections.length - 1];
			const currentColumn = currentSection.columns[currentSection.columns.length - 1];
			currentColumn.fields.push(field);
		}
	}

	// Clean up empty sections/tabs
	return {
		tabs: layout.tabs.filter((tab) => {
			tab.sections = tab.sections.filter((section) => {
				section.columns = section.columns.filter((col) => col.fields.length > 0);
				return section.columns.length > 0 || section.label;
			});
			return tab.sections.length > 0 || tab.label;
		}),
	};
}
