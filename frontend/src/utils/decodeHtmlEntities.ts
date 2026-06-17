/**
 * Decode common HTML entities without using innerHTML parsing,
 * which can strip or mangle raw XML/JSX tags in message content.
 */
export function decodeHtmlEntities(text: string): string {
	return text
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&quot;/g, '"')
		.replace(/&#39;/g, "'")
		.replace(/&amp;/g, '&');
}
