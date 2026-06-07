/**
 * HTML/SVG sanitization utilities using DOMPurify.
 *
 * Used to sanitize untrusted content (e.g. AI-generated artifacts)
 * before rendering via dangerouslySetInnerHTML.
 */

import DOMPurify from 'dompurify';

/**
 * Sanitize an SVG string, removing dangerous elements and attributes
 * (e.g. event handlers, foreign-object script injection) while preserving
 * valid SVG markup.
 */
export function sanitizeSVG(dirty: string): string {
	return DOMPurify.sanitize(dirty, {
		USE_PROFILES: { svg: true, svgFilters: true },
	});
}
