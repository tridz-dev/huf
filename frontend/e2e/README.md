# E2E tests (Playwright)

These specs run against a real bench serving the built React app at `/huf/`.
CI runs them via `.github/workflows/e2e-tests.yml`.

## Running locally

1. Start a bench with the huf app installed and the frontend built
   (`npm run build` here writes to `huf/public/frontend` and `huf/www/huf.html`).
2. Seed the fixtures the specs rely on:

   ```bash
   bench --site <site> execute huf.ai.tests.fixtures.seed_e2e_data.seed
   ```

   The seeder is idempotent and reads these env vars:
   - `E2E_LLM_PROVIDER_API_KEY` — real provider key (falls back to a placeholder)
   - `E2E_PROVIDER_NAME` (default `E2E OpenAI`)
   - `E2E_LLM_MODEL` (default `openai/gpt-4o-mini`)
   - `E2E_TEST_AGENT` (default `Test New UI` — must match `TEST_AGENT` in the specs)
3. Run the tests from this directory:

   ```bash
   E2E_BASE_URL=http://127.0.0.1:8000/huf/ E2E_USER=Administrator E2E_PASSWORD=admin npx playwright test
   ```

   `E2E_BASE_URL` overrides the private-IP local-dev default in
   `playwright.config.ts`. `auth.setup.ts` logs in once and reuses the
   storage state for all specs.

## CI secret

The LLM-dependent specs (the chat response test in `chat.spec.ts` and
`agent-tool-call.spec.ts`) need a real provider key. Add the
`E2E_LLM_PROVIDER_API_KEY` repository secret (Settings > Secrets and
variables > Actions). Without it the seeder writes a placeholder key: all
UI-only and network-mocked specs still pass, the two LLM-dependent tests
fail.
