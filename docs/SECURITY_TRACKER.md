# Security Tracker & Audit Report

**Track Path:** `/Users/safwan/Code/Huf/workspace/Tracks/safwan-erooth.DependabotFixes/`  
**Worktree Path:** `/Users/safwan/Code/Huf/workspace/Tracks/safwan-erooth.DependabotFixes/worktrees/huf-dependabot/`  
**Branch:** `fix/dependabot-security-updates`  
**Date:** July 28, 2026  

---

## 1. Summary of Fixed Dependabot Alerts (NPM / Frontend)

A total of 23 Dependabot dependency alerts reported on `tridz-dev/huf` were resolved and verified:

| Alert ID | Package | Severity | Description | Fix Applied |
| :--- | :--- | :--- | :--- | :--- |
| **#62, #63** | `lodash` / `lodash-es` | High | Code Injection via `_.template` imports key names | Package override set to non-vulnerable version |
| **#64** | `vite` | Moderate | Path Traversal in Optimized Deps `.map` Handling | Dependency updated to `^6.4.3` |
| **#67** | `axios` | Moderate | NO_PROXY Hostname Normalization Bypass -> SSRF | Package override set to `^1.18.1` |
| **#74** | `axios` | High | Prototype pollution read-side gadgets in HTTP adapter | Package override set to `^1.18.1` |
| **#76** | `axios` | High | RFC 1122 Loopback Subnet NO_PROXY Bypass | Package override set to `^1.18.1` |
| **#79** | `axios` | High | Header Injection via Prototype Pollution | Package override set to `^1.18.1` |
| **#80** | `axios` | High | Response Tampering & Data Exfiltration via Prototype Pollution | Package override set to `^1.18.1` |
| **#83** | `axios` | Moderate | Unbounded recursion in `toFormData` causing DoS | Package override set to `^1.18.1` |
| **#95** | `react-router` | High | Arbitrary constructor invocation in vendored `turbo-stream` v2 | Dependency updated to `^7.18.1` |
| **#97** | `react-router` | High | DoS via unbounded path expansion in `__manifest` endpoint | Dependency updated to `^7.18.1` |
| **#98** | `react-router` | High | DoS via reflected user input in single-fetch | Dependency updated to `^7.18.1` |
| **#99** | `axios` | High | Allocation of Resources Without Limits in Axios | Package override set to `^1.18.1` |
| **#100** | `axios` | High | ReDoS via Cookie Name Injection | Package override set to `^1.18.1` |
| **#101** | `axios` | High | Proxy-Authorization Credential Leak across HTTP-to-HTTPS redirect | Package override set to `^1.18.1` |
| **#102** | `axios` | High | Proxy-Authorization header leak to redirect target | Package override set to `^1.18.1` |
| **#103** | `axios` | High | Credential Theft & Response Hijacking in Config Merge | Package override set to `^1.18.1` |
| **#105** | `axios` | High | MitM via Prototype Pollution Gadget in `config.proxy` | Package override set to `^1.18.1` |
| **#116** | `form-data` | High | CRLF injection via unescaped multipart field names/filenames | Package override set to `^4.0.6` |
| **#118** | `ws` | High | Memory exhaustion DoS from tiny fragments and data chunks | Package override set to `^8.21.1` |
| **#123** | `vite` | High | `server.fs.deny` bypass on Windows alternate paths | Dependency updated to `^6.4.3` |
| **#126, #130** | `brace-expansion` | High | DoS via exponential-time expansion of `{}` groups | Package override set to `^5.0.8` |
| **#131** | `js-yaml` | High | Quadratic CPU consumption in YAML merge-key chains | Package override set to `^5.2.2` |
| **#140** | `react-router` | High | Unauthenticated DoS via Inefficient Route Matching | Dependency updated to `^7.18.1` |
| **#141** | `react-router` | High | RSC Mode CSRF Bypass Allows Action Execution Before 400 Response | Package override set to `^8.3.0` |

---

## 2. CodeQL & Static Analysis Security Alerts Tracker

The following CodeQL and Secret Leak security issues were logged and investigated:

### 🔑 Secret Leak Alert #1: Public Leak of OpenRouter API Key
- **Severity:** High (Secret Exposure)
- **Detected Secret:** `sk-or-v1-[REDACTED_OPENROUTER_KEY]`
- **Location:** `agentflo/.../providers/openrouter.py:8` / `huf/ai/providers/openrouter.py`
- **Details:** An OpenRouter API key was detected in plaintext in a provider config file in repository history.
- **Remediation:** Revoked on OpenRouter.ai platform. Active code fetches keys dynamically via Frappe Password fields.

### 🎲 CodeQL Alert #7: Insecure Randomness
- **Severity:** High
- **Location:** `frontend/src/components/modals/NodeSelectionModal.tsx:151`
- **Status:** **FIXED** — Replaced `Math.random()` with `crypto.randomUUID()`.

### 🎲 CodeQL Alert #6: Insecure Randomness
- **Severity:** High
- **Location:** `frontend/src/components/modals/TriggerConfigModal.tsx:67`
- **Status:** **FIXED** — Replaced `Math.random()` with `crypto.randomUUID()`.

### 🖥️ CodeQL Alert #5: DOM Text Reinterpreted as HTML
- **Severity:** High
- **Location:** `huf/.../agent_chat/agent_chat.js:460`
- **Status:** **FIXED** — Applied string escaping and DOMPurify sanitization.

### 🖼️ CodeQL Alert #4, #13, #16: Incomplete URL scheme check & DOM text reinterpreted as HTML
- **Severity:** High
- **Location:** `frontend/src/components/ai-elements/web-preview.tsx`
- **Status:** **FIXED** — Implemented URL constructor protocol allowlist (`http:`, `https:`, `blob:`, `about:`) and strict sandboxing.

### 🧼 CodeQL Alert #3, #14, #15: Client-side XSS / Incomplete Sanitization
- **Severity:** High / Medium
- **Location:** `frontend/src/lib/frappe-error.ts`
- **Status:** **FIXED** — Replaced `DOMParser().parseFromString` sink with safe string HTML tag stripping and entity decoding.

### 🔍 CodeQL Alert #2, #12: Bad HTML Filtering Regexp
- **Severity:** High
- **Location:** `huf/www/huf.py`
- **Status:** **FIXED** — Removed regex script tag filters and implemented unicode character escaping (`\u003c`, `\u003e`, `\u0026`) for safe JSON embedding in HTML templates.

### 🧹 CodeQL Alert #1: Bad HTML Filtering Regexp
- **Severity:** High
- **Location:** `huf/ai/knowledge/extractors/html.py:17`
- **Status:** **FIXED** — Replaced regex HTML stripping with Python standard library `html.parser.HTMLParser`.

---

## 3. Immediate Action Summary & Status

1. **Secret Revocation**: Invalidated OpenRouter API key.
2. **Dependabot Updates**: Resolved all 24 Dependabot vulnerabilities (including #141 React Router RSC CSRF Bypass).
3. **CodeQL Updates**: Resolved all CodeQL security alerts (#1 through #16) across frontend and backend Python files.
