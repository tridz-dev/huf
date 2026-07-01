/**
 * Extracts safe `const`/`let` preamble bindings from AI-generated JSX artifacts.
 *
 * LLMs often emit small React snippets with top-level declarations before JSX.
 * react-jsx-parser only accepts JSX markup, so we split the preamble, evaluate
 * literal-only expressions via AST walking (no eval), and pass bindings through.
 */

import * as acorn from 'acorn';
import type {
	Expression,
	Program,
	VariableDeclaration,
	ArrayExpression,
	ObjectExpression,
	Identifier,
	MemberExpression,
	TemplateLiteral,
	UnaryExpression,
	Literal,
} from 'estree';

export interface JsxPreambleResult {
	jsx: string;
	bindings: Record<string, unknown>;
	warnings: string[];
}

const DECLARATION_KEYWORD = /^(?:const|let|var)\b/;

/**
 * Split AI output into optional JS preamble and JSX body.
 */
export function splitPreambleAndJsx(source: string): { preamble: string; jsx: string } {
	const trimmed = source.trim();
	if (!trimmed) {
		return { preamble: '', jsx: '' };
	}

	let pos = 0;
	while (pos < trimmed.length) {
		pos = skipWhitespaceAndComments(trimmed, pos);
		if (pos >= trimmed.length) {
			break;
		}

		const rest = trimmed.slice(pos);
		if (DECLARATION_KEYWORD.test(rest)) {
			const keywordMatch = rest.match(DECLARATION_KEYWORD);
			if (!keywordMatch) {
				break;
			}
			pos += keywordMatch[0].length;
			pos = skipWhitespaceAndComments(trimmed, pos);
			pos = findStatementEnd(trimmed, pos);
			if (pos < trimmed.length && trimmed[pos] === ';') {
				pos++;
			}
			continue;
		}

		if (trimmed[pos] === '<') {
			return {
				preamble: trimmed.slice(0, pos).trim(),
				jsx: trimmed.slice(pos).trim(),
			};
		}

		// Unrecognized leading syntax — treat entire input as JSX.
		return { preamble: '', jsx: trimmed };
	}

	return { preamble: trimmed, jsx: '' };
}

/**
 * Parse preamble declarations and return bindings plus the JSX body.
 * On failure, returns the original source as JSX with empty bindings.
 */
export function extractJsxAndBindings(source: string): JsxPreambleResult {
	const warnings: string[] = [];
	const { preamble, jsx } = splitPreambleAndJsx(source);

	if (!preamble) {
		return { jsx: jsx || source.trim(), bindings: {}, warnings };
	}

	try {
		const program = acorn.parse(preamble, {
			ecmaVersion: 2020,
			sourceType: 'script',
		}) as Program;

		const bindings: Record<string, unknown> = {};

		for (const statement of program.body) {
			if (statement.type !== 'VariableDeclaration') {
				throw new Error(`Unsupported preamble statement: ${statement.type}`);
			}
			evaluateVariableDeclaration(statement as VariableDeclaration, bindings);
		}

		if (!jsx) {
			warnings.push('Preamble parsed but no JSX body found');
		}

		return { jsx: jsx || source.trim(), bindings, warnings };
	} catch (error) {
		warnings.push(
			error instanceof Error ? error.message : 'Failed to parse JSX preamble'
		);
		return { jsx: source.trim(), bindings: {}, warnings };
	}
}

function skipWhitespaceAndComments(source: string, start: number): number {
	let pos = start;
	while (pos < source.length) {
		if (/\s/.test(source[pos])) {
			pos++;
			continue;
		}
		if (source.slice(pos, pos + 2) === '//') {
			pos += 2;
			while (pos < source.length && source[pos] !== '\n') {
				pos++;
			}
			continue;
		}
		if (source.slice(pos, pos + 2) === '/*') {
			const end = source.indexOf('*/', pos + 2);
			pos = end === -1 ? source.length : end + 2;
			continue;
		}
		break;
	}
	return pos;
}

function findStatementEnd(source: string, start: number): number {
	let pos = start;
	let depthParen = 0;
	let depthBracket = 0;
	let depthBrace = 0;
	let inString: '"' | "'" | '`' | null = null;
	let escaped = false;

	while (pos < source.length) {
		const ch = source[pos];

		if (inString) {
			if (escaped) {
				escaped = false;
			} else if (ch === '\\') {
				escaped = true;
			} else if (ch === inString) {
				inString = null;
			}
			pos++;
			continue;
		}

		if (ch === '"' || ch === "'" || ch === '`') {
			inString = ch;
			pos++;
			continue;
		}

		if (ch === '(') depthParen++;
		else if (ch === ')') depthParen = Math.max(0, depthParen - 1);
		else if (ch === '[') depthBracket++;
		else if (ch === ']') depthBracket = Math.max(0, depthBracket - 1);
		else if (ch === '{') depthBrace++;
		else if (ch === '}') depthBrace = Math.max(0, depthBrace - 1);
		else if (
			ch === ';' &&
			depthParen === 0 &&
			depthBracket === 0 &&
			depthBrace === 0
		) {
			return pos;
		}

		pos++;
	}

	return pos;
}

function evaluateVariableDeclaration(
	declaration: VariableDeclaration,
	bindings: Record<string, unknown>
): void {
	if (declaration.kind === 'var') {
		throw new Error('Only const/let declarations are allowed in JSX preamble');
	}

	for (const declarator of declaration.declarations) {
		if (declarator.type !== 'VariableDeclarator') {
			throw new Error('Unsupported declarator type');
		}
		if (declarator.id.type !== 'Identifier') {
			throw new Error('Only simple identifier bindings are supported');
		}
		if (!declarator.init) {
			throw new Error(`Missing initializer for ${declarator.id.name}`);
		}

		const value = evaluateExpression(declarator.init as Expression, bindings);
		bindings[declarator.id.name] = value;
	}
}

function evaluateExpression(
	node: Expression,
	bindings: Record<string, unknown>
): unknown {
	switch (node.type) {
		case 'Literal':
			return (node as Literal).value;
		case 'ArrayExpression':
			return (node as ArrayExpression).elements.map((element) => {
				if (element === null) {
					throw new Error('Array holes are not supported in JSX preamble');
				}
				if (element.type === 'SpreadElement') {
					throw new Error('Spread elements are not supported in JSX preamble');
				}
				return evaluateExpression(element, bindings);
			});
		case 'ObjectExpression':
			return (node as ObjectExpression).properties.reduce<Record<string, unknown>>(
				(acc, prop) => {
					if (prop.type !== 'Property' || prop.kind !== 'init') {
						throw new Error('Only plain object properties are supported');
					}
					const key =
						prop.key.type === 'Identifier'
							? prop.key.name
							: prop.key.type === 'Literal' && typeof prop.key.value === 'string'
								? prop.key.value
								: null;
					if (!key) {
						throw new Error('Only identifier or string keys are supported');
					}
					acc[key] = evaluateExpression(prop.value as Expression, bindings);
					return acc;
				},
				{}
			);
		case 'Identifier': {
			const name = (node as Identifier).name;
			if (!(name in bindings)) {
				throw new Error(`Unknown binding: ${name}`);
			}
			return bindings[name];
		}
		case 'MemberExpression': {
			const member = node as MemberExpression;
			const object = evaluateExpression(member.object as Expression, bindings);
			const property = member.computed
				? evaluateExpression(member.property as Expression, bindings)
				: member.property.type === 'Identifier'
					? member.property.name
					: null;
			if (property === null || property === undefined) {
				throw new Error('Unsupported member expression');
			}
			if (object === null || typeof object !== 'object') {
				throw new Error('Invalid member access target');
			}
			return (object as Record<string | number, unknown>)[property as string | number];
		}
		case 'TemplateLiteral': {
			const template = node as TemplateLiteral;
			let result = '';
			for (let i = 0; i < template.quasis.length; i++) {
				result += template.quasis[i].value.cooked ?? template.quasis[i].value.raw;
				const expression = template.expressions[i];
				if (expression) {
					result += String(evaluateExpression(expression, bindings));
				}
			}
			return result;
		}
		case 'UnaryExpression': {
			const unary = node as UnaryExpression;
			if (unary.operator === '-' && unary.argument.type === 'Literal') {
				return -((unary.argument as Literal).value as number);
			}
			throw new Error(`Unsupported unary operator: ${unary.operator}`);
		}
		default:
			throw new Error(`Unsupported expression type: ${node.type}`);
	}
}
