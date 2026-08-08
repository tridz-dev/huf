import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface FormSettingsSectionProps {
	title: React.ReactNode;
	description: string;
	children: React.ReactNode;
	className?: string;
}

export function FormSettingsSection({
	title,
	description,
	children,
	className,
}: FormSettingsSectionProps) {
	return (
		<div
			className={cn(
				'grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-10',
				className,
			)}
		>
			<div className="space-y-1">
				<h3 className="text-lg font-semibold tracking-tight">{title}</h3>
				<p className="text-sm text-steel">{description}</p>
			</div>
			<Card>
				<CardContent className="grid gap-6 pt-6">{children}</CardContent>
			</Card>
		</div>
	);
}
