import { FrappeApp } from 'frappe-js-sdk';

// Initialize Frappe App instance
const frappeUrl = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

export const frappe = new FrappeApp(frappeUrl);

export const auth = frappe.auth();
export const db = frappe.db();
export const call = frappe.call();
