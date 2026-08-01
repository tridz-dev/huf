import { FrappeApp } from 'frappe-js-sdk';
import { createCsrfRetryHandler } from './csrfRetryInterceptor';
import { createSessionInvalidationHandler } from './sessionInvalidation';

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
 * whitelisted" - on whichever API call happens to notice it first. We confirm
 * the session is actually dead with a lightweight token request before
 * triggering a logout, so transient blips (cold worker, cache clear, cookie
 * race) don't sign the user out of an otherwise valid session.
 */
frappe.axios.interceptors.response.use(
  (response) => response,
  createSessionInvalidationHandler(frappe.axios),
);
