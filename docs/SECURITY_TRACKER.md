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

---

## 2. CodeQL & Static Analysis Security Alerts Tracker

The following CodeQL and Secret Leak security issues were logged and investigated:

### 🔑 Secret Leak Alert #1: Public Leak of OpenRouter API Key
- **Severity:** High (Secret Exposure)
- **Detected Secret:** `sk-or-v1-[REDACTED_OPENROUTER_KEY]`
- **Location:** `agentflo/.../providers/openrouter.py:8` / `huf/ai/providers/openrouter.py`
- **Details:** An OpenRouter API key was detected in plaintext in a provider config file in repository history.
- **Remediation Required:**
  1. Revoke the key immediately on OpenRouter platform dashboard.
  2. Ensure all provider keys are loaded dynamically from Frappe Password fields (`frappe.get_doc("AI Provider", ...).get_password("api_key")`) or environment variables, never hardcoded.

### 🎲 CodeQL Alert #7: Insecure Randomness
- **Severity:** High
- **Location:** `frontend/src/components/modals/NodeSelectionModal.tsx:151`
- **Snippet:** `apiKey: Math.random().toString(36).substring(2, 15)`
- **Issue:** Using `Math.random()` to generate security-sensitive tokens/keys (like API keys) is predictable.
- **Remediation:** Replace with `window.crypto.getRandomValues()` or `crypto.randomUUID()`.

### 🎲 CodeQL Alert #6: Insecure Randomness
- **Severity:** High
- **Location:** `frontend/src/components/modals/TriggerConfigModal.tsx:67`
- **Snippet:** `apiKey: Math.random().toString(36).substring(2, 15)`
- **Issue:** Using `Math.random()` for generating webhook API keys is insecure.
- **Remediation:** Replace with `window.crypto.getRandomValues()` or `crypto.randomUUID()`.

### 🖥️ CodeQL Alert #5: DOM Text Reinterpreted as HTML
- **Severity:** High
- **Location:** `huf/.../agent_chat/agent_chat.js:460`
- **Issue:** Directly assigning untrusted text/message content to `.innerHTML` or jQuery `$(...).html()` without HTML escaping or DOMPurify sanitization.
- **Remediation:** Use `.textContent` / `.innerText` or sanitize content with DOMPurify before assigning to HTML.

### 🖼️ CodeQL Alert #4: DOM Text Reinterpreted as HTML
- **Severity:** High
- **Location:** `frontend/src/components/ai-elements/web-preview.tsx:189`
- **Issue:** Embedding dynamic HTML string or URL inside an iframe without proper origin isolation or restrictive sandbox flags.
- **Remediation:** Ensure restrictive sandbox attributes (`sandbox="allow-scripts"` without `allow-same-origin`) and validate URLs.

### 🧼 CodeQL Alert #3: Incomplete Multi-Character Sanitization
- **Severity:** High
- **Location:** `frontend/src/lib/frappe-error.ts:114`
- **Snippet:** `return message.replace(/<[^>]*>/g, '');`
- **Issue:** Single-pass regex replacement `/<[^>]*>/g` can be bypassed by nested tags (e.g. `<sc<script>ript>`).
- **Remediation:** Use `DOMParser` or `DOMPurify.sanitize(str, { ALLOWED_TAGS: [] })` to strip tags safely.

### 🔍 CodeQL Alert #2: Bad HTML Filtering Regexp
- **Severity:** High
- **Location:** `huf/www/huf.py:11`
- **Snippet:** `SCRIPT_TAG_PATTERN = re.compile(r"\<script[^<]*\</script\>")`
- **Issue:** The regex for finding script tags fails on tag attributes containing `<` or case variations.
- **Remediation:** Use a robust HTML parser (like `bs4.BeautifulSoup` or `html.parser`) or proper escaping instead of fragile regex tag stripping.

### 🧹 CodeQL Alert #1: Bad HTML Filtering Regexp
- **Severity:** High
- **Location:** `huf/ai/knowledge/extractors/html.py:17`
- **Snippet:** `html_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)`
- **Issue:** Fragile regex tag stripping causes incomplete sanitization or ReDoS when extracting clean text from HTML documents.
- **Remediation:** Replace regex-based HTML stripping with BeautifulSoup (`BeautifulSoup(html_content, "html.parser").get_text()`).

---

## 3. Recommended Immediate Action Items

1. **Secret Revocation**: Invalidate the leaked OpenRouter API key on openrouter.ai.
2. **Apply CodeQL Patches**:
   - Replace `Math.random()` with `crypto.randomUUID()` in `NodeSelectionModal.tsx` and `TriggerConfigModal.tsx`.
   - Update `frappe-error.ts` to use `DOMParser` for tag stripping.
   - Update `huf/www/huf.py` and `huf/ai/knowledge/extractors/html.py` to use proper HTML parsers instead of fragile regexes.
