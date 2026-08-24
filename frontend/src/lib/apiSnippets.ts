/**
 * Minimal multi-language code-snippet generator for the Developer API docs.
 *
 * Deliberately hand-rolled rather than pulling in a HAR-based snippet
 * library (e.g. httpsnippet): we only ever render a handful of fixed
 * endpoints x 2 auth modes x 4 languages, which a small pure function
 * covers with no added dependency or bundle weight.
 */

export type SnippetLanguage = 'curl' | 'python' | 'javascript' | 'typescript';
export type AuthMode = 'apiKey' | 'session';

export interface SnippetRequest {
	method: 'GET' | 'POST';
	path: string;
	/** Form-encoded body params, POST only. */
	body?: Record<string, string>;
}

const API_KEY_PLACEHOLDER = 'huf_sk_...';
const SESSION_ID_PLACEHOLDER = '<sid-from-login>';

function bodyToFormString(body: Record<string, string>): string {
	return Object.entries(body)
		.map(([key, value]) => `${key}=${value}`)
		.join('&');
}

function buildCurl(baseUrl: string, request: SnippetRequest, authMode: AuthMode): string {
	const url = `${baseUrl}${request.path}`;
	const authHeader =
		authMode === 'apiKey'
			? `-H "X-Huf-Api-Key: ${API_KEY_PLACEHOLDER}" \\\n  `
			: `-H "Cookie: sid=${SESSION_ID_PLACEHOLDER}" \\\n  `;
	const bodyFlag = request.body
		? Object.entries(request.body)
				.map(([key, value]) => `-d "${key}=${value}" \\\n  `)
				.join('')
		: '';
	const methodFlag = request.method === 'POST' ? '-X POST \\\n  ' : '';

	return `curl ${methodFlag}"${url}" \\\n  ${authHeader}${bodyFlag}`.replace(/ \\\n  $/, '');
}

function buildPython(baseUrl: string, request: SnippetRequest, authMode: AuthMode): string {
	const url = `${baseUrl}${request.path}`;
	const authArg =
		authMode === 'apiKey'
			? `headers={"X-Huf-Api-Key": "${API_KEY_PLACEHOLDER}"}`
			: `cookies={"sid": "${SESSION_ID_PLACEHOLDER}"}`;
	const method = request.method === 'POST' ? 'post' : 'get';
	const dataArg = request.body ? `, data=${JSON.stringify(request.body)}` : '';

	return `import requests\n\nresponse = requests.${method}(\n    "${url}",\n    ${authArg}${dataArg},\n)\nprint(response.json())`;
}

function buildJavaScript(baseUrl: string, request: SnippetRequest, authMode: AuthMode, ts: boolean): string {
	const url = `${baseUrl}${request.path}`;
	const headerLine =
		authMode === 'apiKey'
			? `headers: { "X-Huf-Api-Key": "${API_KEY_PLACEHOLDER}" },`
			: `credentials: "include", // browser sends the sid cookie automatically once logged in`;
	const bodyLine = request.body
		? `\n  body: new URLSearchParams(${JSON.stringify(request.body)}),`
		: '';
	const methodLine = request.method === 'POST' ? `\n  method: "POST",` : '';
	const typeAnnotation = ts ? ': Response' : '';

	return `const response${typeAnnotation} = await fetch("${url}", {${methodLine}\n  ${headerLine}${bodyLine}\n});\nconst data = await response.json();\nconsole.log(data);`;
}

export function buildSnippet(
	baseUrl: string,
	request: SnippetRequest,
	language: SnippetLanguage,
	authMode: AuthMode,
): string {
	switch (language) {
		case 'curl':
			return buildCurl(baseUrl, request, authMode);
		case 'python':
			return buildPython(baseUrl, request, authMode);
		case 'javascript':
			return buildJavaScript(baseUrl, request, authMode, false);
		case 'typescript':
			return buildJavaScript(baseUrl, request, authMode, true);
	}
}

/**
 * Session auth needs a real sid, which -- unlike an API key -- isn't
 * something a developer can generate and paste in ahead of time. Shown as a
 * prerequisite step whenever authMode is "session".
 */
export function buildLoginSnippet(baseUrl: string, language: SnippetLanguage): string {
	const loginRequest: SnippetRequest = {
		method: 'POST',
		path: '/api/method/login',
		body: { usr: 'you@example.com', pwd: 'your-password' },
	};

	if (language === 'curl') {
		const url = `${baseUrl.replace(/\/huf\/api\/v1$/, '')}${loginRequest.path}`;
		return `curl -X POST "${url}" \\\n  -d "usr=you@example.com" \\\n  -d "pwd=your-password" \\\n  -c cookies.txt\n# cookies.txt now holds the sid to reuse in subsequent requests`;
	}
	if (language === 'python') {
		const url = `${baseUrl.replace(/\/huf\/api\/v1$/, '')}${loginRequest.path}`;
		return `import requests\n\nsession = requests.Session()\nsession.post("${url}", data={"usr": "you@example.com", "pwd": "your-password"})\n# session.cookies now holds the sid; reuse \`session\` for subsequent requests`;
	}
	const url = `${baseUrl.replace(/\/huf\/api\/v1$/, '')}${loginRequest.path}`;
	const typeAnnotation = language === 'typescript' ? ': Response' : '';
	return `const login${typeAnnotation} = await fetch("${url}", {\n  method: "POST",\n  credentials: "include",\n  body: new URLSearchParams({ usr: "you@example.com", pwd: "your-password" }),\n});\n// the browser now holds the sid cookie for subsequent same-origin requests`;
}
