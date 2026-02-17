/**
 * Parser for AI-generated artifacts in message content.
 *
 * Detects and extracts artifact blocks from AI responses using XML-style tags:
 * <artifact type="code" language="python" title="Hello World">
 * print("Hello, World!")
 * </artifact>
 */

import type {
	ParsedArtifact,
	ArtifactType,
	ArtifactParseResult,
} from '@/types/artifact.types';

// Regex to match artifact tags with attributes and content
// Matches: <artifact type="code" language="python" title="Hello">content</artifact>
const ARTIFACT_REGEX = /<artifact\s+([^>]*)>([\s\S]*?)<\/artifact>/gi;

// Regex to extract individual attributes from the tag
const ATTR_REGEX = /(\w+)=["']([^"']*)["']/g;

/**
 * Parse artifact blocks from content string.
 *
 * @param content - The raw content string potentially containing artifact blocks
 * @returns Object with remaining text and extracted artifacts
 */
export function parseArtifacts(content: string): ArtifactParseResult {
	const artifacts: ParsedArtifact[] = [];
	let index = 0;

	// Reset regex lastIndex to ensure we start from the beginning
	ARTIFACT_REGEX.lastIndex = 0;

	const text = content.replace(ARTIFACT_REGEX, (_match, attrs, body) => {
		const attributes: Record<string, string> = {};

		// Reset ATTR_REGEX for each match
		ATTR_REGEX.lastIndex = 0;
		let attrMatch;
		while ((attrMatch = ATTR_REGEX.exec(attrs)) !== null) {
			attributes[attrMatch[1]] = attrMatch[2];
		}

		const artifact: ParsedArtifact = {
			id: `artifact-${Date.now()}-${index}`,
			type: (attributes.type || 'code') as ArtifactType,
			title: attributes.title,
			language: attributes.language,
			content: body.trim(),
		};

		artifacts.push(artifact);
		index++;

		// Return a placeholder that can be used for positioning if needed
		return `\n[ARTIFACT_PLACEHOLDER_${index - 1}]\n`;
	});

	// Clean up the text by removing placeholder markers and extra whitespace
	const cleanedText = text
		.replace(/\n?\[ARTIFACT_PLACEHOLDER_\d+\]\n?/g, '\n\n')
		.replace(/\n{3,}/g, '\n\n')
		.trim();

	return { text: cleanedText, artifacts };
}

/**
 * Check if content contains any artifact blocks.
 *
 * @param content - The content string to check
 * @returns True if content contains at least one artifact block
 */
export function hasArtifacts(content: string): boolean {
	if (!content) return false;
	// Reset regex lastIndex
	ARTIFACT_REGEX.lastIndex = 0;
	return ARTIFACT_REGEX.test(content);
}

/**
 * Extract just the artifacts without modifying the text.
 *
 * @param content - The content string to extract from
 * @returns Array of parsed artifacts
 */
export function extractArtifacts(content: string): ParsedArtifact[] {
	return parseArtifacts(content).artifacts;
}

/**
 * Validate an artifact type string.
 *
 * @param type - The type string to validate
 * @returns True if the type is a valid ArtifactType
 */
export function isValidArtifactType(type: string): type is ArtifactType {
	const validTypes: ArtifactType[] = [
		'code',
		'document',
		'html',
		'svg',
		'mermaid',
		'react-component',
		'markdown',
	];
	return validTypes.includes(type as ArtifactType);
}
