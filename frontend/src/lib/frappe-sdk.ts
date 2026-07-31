import { FrappeApp } from 'frappe-js-sdk';
import { createCsrfRetryHandler } from './csrfRetryInterceptor';
import { isSessionInvalidatedError, notifySessionInvalidated } from './sessionInvalidation';

// Initialize Frappe App instance
const frappeUrl = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

export const frappe = new FrappeApp(frappeUrl);

export const auth = frappe.auth();
export const db = frappe.db();
export const call = frappe.call();
export const file = frappe.file();

frappe.axios.interceptors.response.use((response) => response, createCsrfRetryHandler(frappe.axios));

/**
 * A session that's genuinely gone (see sessionInvalidation.ts) surfaces
 * identically to a one-off feature-permission denial - "Function X is not
 * whitelisted" - on whichever API call happens to notice it first. Route
 * that straight to a clean, immediate sign-out instead of letting each page
 * show its own confusing "permission denied" toast for what is actually a
 * dead session.
 */
frappe.axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (isSessionInvalidatedError(error)) {
      notifySessionInvalidated();
    }
    return Promise.reject(error);
  },
);
