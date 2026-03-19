/**
 * UI Component Registry
 *
 * Maps <ui-component type="..."> type strings to their React renderer
 * components.  Add new renderers here to make them available in chat.
 */

import type { ComponentType } from 'react';
import type { ParsedUIComponent } from '@/types/artifact.types';

export interface UIComponentRendererProps {
	component: ParsedUIComponent;
}

// Lazy-loaded registry — keeps the main bundle lean. Each renderer is only
// imported when actually needed.
import { StatsCardRenderer } from './renderers/StatsCardRenderer';
import { KPIGridRenderer } from './renderers/KPIGridRenderer';
import { BarChartRenderer } from './renderers/BarChartRenderer';
import { LineChartRenderer } from './renderers/LineChartRenderer';
import { PieChartRenderer } from './renderers/PieChartRenderer';
import { AreaChartRenderer } from './renderers/AreaChartRenderer';
import { DataTableRenderer } from './renderers/DataTableRenderer';
import { ProgressCardRenderer } from './renderers/ProgressCardRenderer';
import { InfoCardRenderer } from './renderers/InfoCardRenderer';

const registry: Record<string, ComponentType<UIComponentRendererProps>> = {
	'stats-card': StatsCardRenderer,
	'kpi-grid': KPIGridRenderer,
	'bar-chart': BarChartRenderer,
	'line-chart': LineChartRenderer,
	'pie-chart': PieChartRenderer,
	'area-chart': AreaChartRenderer,
	'data-table': DataTableRenderer,
	'progress-card': ProgressCardRenderer,
	'info-card': InfoCardRenderer,
};

export function getUIComponentRenderer(type: string): ComponentType<UIComponentRendererProps> | null {
	return registry[type] ?? null;
}

export function getRegisteredComponentTypes(): string[] {
	return Object.keys(registry);
}
