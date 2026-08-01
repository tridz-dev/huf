import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _csrfRetried?: boolean;
}

/**
 * `window.csrf_token` is only ever set once, from the server-rendered boot
 * HTML (huf/www/huf.py). Frappe can regenerate the session's real CSRF
 * token independently (e.g. after a worker restart or cache clear), which
 * makes every write in an already-open tab fail with a 400 CSRFTokenError
 * even though the session cookie itself is still valid. Refresh the token
 * once and retry instead of surfacing that as a broken/logged-out session.
 */
export function createCsrfRetryHandler(axiosInstance: AxiosInstance) {
  return async (error: AxiosError<{ exc_type?: string }>) => {
    const config = error.config as RetriableRequestConfig | undefined;
    const isCsrfError =
      error.response?.status === 400 && error.response?.data?.exc_type === 'CSRFTokenError';

    if (isCsrfError && config && !config._csrfRetried) {
      config._csrfRetried = true;
      try {
        const { data } = await axiosInstance.get('/api/method/huf.ai.session_api.get_csrf_token');
        const freshToken = data?.message;
        if (freshToken) {
          (window as unknown as { csrf_token?: string }).csrf_token = freshToken;
          config.headers.set('X-Frappe-CSRF-Token', freshToken);
          return axiosInstance.request(config);
        }
      } catch {
        // Fall through to the original error - if the token endpoint itself
        // fails, the session is genuinely gone and normal auth handling applies.
      }
    }

    return Promise.reject(error);
  };
}
