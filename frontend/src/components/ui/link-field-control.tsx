import * as React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface LinkFieldActionProps {
	href: string;
	className?: string;
}

export function LinkFieldAction({ href, className }: LinkFieldActionProps) {
	const navigate = useNavigate();

	return (
		<button
			type="button"
			className={cn(
				'inline-flex shrink-0 items-center justify-center rounded-sm p-0.5 text-muted-foreground/50 transition-colors hover:bg-muted/70 hover:text-foreground',
				className
			)}
			title="Open record"
			aria-label="Open record"
			onClick={(e) => {
				e.preventDefault();
				e.stopPropagation();
				navigate(href);
			}}
		>
			<ArrowUpRight className="h-3.5 w-3.5" />
		</button>
	);
}

export interface LinkFieldControlProps {
	value?: string;
	linkTo?: (value: string) => string | undefined;
	disabled?: boolean;
	children: React.ReactNode;
	className?: string;
}

export function LinkFieldControl({
	value,
	linkTo,
	disabled = false,
	children,
	className,
}: LinkFieldControlProps) {
	const href = value && linkTo ? linkTo(value) : undefined;
	const showLink = Boolean(href) && !disabled;

	return (
		<div
			className={cn(
				'relative w-full',
				showLink && '[&>button>span]:pr-5',
				className
			)}
		>
			{children}
			{showLink && href ? (
				<LinkFieldAction
					href={href}
					className="absolute right-8 top-1/2 z-10 -translate-y-1/2"
				/>
			) : null}
		</div>
	);
}
