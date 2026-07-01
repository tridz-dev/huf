/**
 * Fixes common JSX syntax mistakes in AI-generated chart artifacts.
 *
 * LLMs often omit backticks on template literals, skip `||` fallbacks, etc.
 * These are safe string transforms applied after preamble extraction.
 */

/**
 * Apply heuristic fixes to JSX markup before passing to react-jsx-parser.
 */
export function fixCommonJsxMistakes(jsx: string): string {
	if (!jsx) return jsx;

	let result = jsx;

	// [AED ${value}, "Amount"] → [`AED ${value}`, "Amount"]
	result = result.replace(
		/\[\s*([A-Za-z_][\w]*)\s+\$\{([^}]+)\}\s*,/g,
		'[`$1 ${$2}`,'
	);

	// key={cell-${idx}} → key={`cell-${idx}`}
	result = result.replace(
		/key=\{([a-zA-Z_][\w-]*)-\$\{([^}]+)\}\}/g,
		'key={`$1-${$2}`}'
	);

	// colors[entry.status]  "#8884d8" → colors[entry.status] || "#8884d8"
	result = result.replace(
		/(\w+\[[^\]]+\])\s+(["']#[0-9A-Fa-f]{3,8}["'])/g,
		'$1 || $2'
	);

	return result;
}
