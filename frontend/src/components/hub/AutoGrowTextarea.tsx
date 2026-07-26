import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';

const MAX_HEIGHT = 168; // ~7 lines of text-sm

/**
 * Textarea that grows with its content up to MAX_HEIGHT, then scrolls.
 * Drops in as a replacement for the fixed rows={1} hub composer inputs.
 */
export const AutoGrowTextarea = forwardRef<
	HTMLTextAreaElement,
	React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function AutoGrowTextarea({ value, style, ...props }, forwardedRef) {
	const innerRef = useRef<HTMLTextAreaElement>(null);
	useImperativeHandle(forwardedRef, () => innerRef.current as HTMLTextAreaElement);

	useEffect(() => {
		const el = innerRef.current;
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
		el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden';
	}, [value]);

	return <textarea ref={innerRef} value={value} rows={1} style={style} {...props} />;
});
