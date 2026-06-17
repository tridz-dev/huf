/**
 * SessionStorage bridge for same-session full-screen preview opens.
 * Stashes parsed preview data before navigating to /huf/view/:messageId.
 */

import type { ParsedMessageContent } from '@/utils/messageContentParser';

const KEY_PREFIX = 'huf-preview:';

export function previewCacheKey(messageId: string): string {
	return `${KEY_PREFIX}${messageId}`;
}

export function writePreviewCache(messageId: string, data: ParsedMessageContent): void {
	try {
		sessionStorage.setItem(previewCacheKey(messageId), JSON.stringify(data));
	} catch {
		// sessionStorage may be unavailable or full
	}
}

export function readPreviewCache(messageId: string): ParsedMessageContent | null {
	try {
		const raw = sessionStorage.getItem(previewCacheKey(messageId));
		if (!raw) return null;
		sessionStorage.removeItem(previewCacheKey(messageId));
		return JSON.parse(raw) as ParsedMessageContent;
	} catch {
		return null;
	}
}
