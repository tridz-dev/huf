import { FrappeApp } from 'frappe-js-sdk';
import { createCsrfRetryHandler } from './csrfRetryInterceptor';

// Initialize Frappe App instance
const frappeUrl = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

export const frappe = new FrappeApp(frappeUrl);

export const auth = frappe.auth();
export const db = frappe.db();
export const call = frappe.call();
export const file = frappe.file();

frappe.axios.interceptors.response.use((response) => response, createCsrfRetryHandler(frappe.axios));
