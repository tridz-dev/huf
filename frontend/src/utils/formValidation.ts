import { UseFormReturn, FieldErrors } from 'react-hook-form';
import { toast } from 'sonner';
import type React from 'react';

/**
 * Maps form fields to their respective tabs
 */
export interface TabFieldMapping {
  [tabName: string]: string[];
}

/**
 * Checks for form errors in tabs that are not currently visible
 * and shows a toast notification if errors are found
 * 
 * @param form - The react-hook-form instance
 * @param activeTab - The currently active tab name
 * @param tabFieldMapping - Object mapping tab names to their field arrays
 * @param tabLabels - Optional object mapping tab names to display labels
 * @returns Array of tab names that have errors
 */
export function checkHiddenTabErrors<T extends Record<string, any>>(
  form: UseFormReturn<T>,
  activeTab: string,
  tabFieldMapping: TabFieldMapping,
  tabLabels?: Record<string, string>
): string[] {
  const errors = form.formState.errors;
  const tabsWithErrors: string[] = [];

  // Check each tab (except the active one) for errors
  Object.entries(tabFieldMapping).forEach(([tabName, fields]) => {
    if (tabName === activeTab) {
      return; // Skip the active tab
    }

    // Check if any field in this tab has an error
    const hasError = fields.some((fieldName) => {
      const fieldError = getNestedError(errors, fieldName);
      return !!fieldError;
    });

    if (hasError) {
      tabsWithErrors.push(tabName);
    }
  });

  // Show toast if there are errors in hidden tabs
  if (tabsWithErrors.length > 0) {
    const tabLabelsToUse = tabLabels || tabFieldMapping;
    const tabNames = tabsWithErrors
      .map((tab) => tabLabelsToUse[tab] || tab)
      .join(', ');
    
    toast.error(
      `Please fix errors in the following tab${tabsWithErrors.length > 1 ? 's' : ''}: ${tabNames}`,
      {
        duration: 5000,
      }
    );
  }

  return tabsWithErrors;
}

/**
 * Helper function to get nested error from field path (e.g., "user.name")
 */
function getNestedError(errors: FieldErrors<any>, fieldPath: string): any {
  const parts = fieldPath.split('.');
  let current: any = errors;
  
  for (const part of parts) {
    if (current && typeof current === 'object' && part in current) {
      current = current[part];
    } else {
      return undefined;
    }
  }
  
  return current;
}

/**
 * Creates a reusable form submit handler that validates all fields,
 * checks for errors in hidden tabs, and calls onSubmit only if validation passes
 * 
 * @param form - The react-hook-form instance
 * @param activeTab - The currently active tab name
 * @param tabFieldMapping - Object mapping tab names to their field arrays
 * @param tabLabels - Optional object mapping tab names to display labels
 * @param onSubmit - The callback function to execute when form is valid
 * @returns A function that can be used as form submit handler or button onClick handler
 */
export function createFormSubmitHandler<T extends Record<string, any>>(
  form: UseFormReturn<T>,
  activeTab: string,
  tabFieldMapping: TabFieldMapping,
  tabLabels: Record<string, string>,
  onSubmit: (values: T) => Promise<void> | void
): (e?: React.FormEvent) => Promise<void> {
  return async (e?: React.FormEvent) => {
    e?.preventDefault();
    
    // Trigger validation on all fields first
    const isValid = await form.trigger();
    
    // Check for errors in hidden tabs after validation
    // This will show toast if there are errors in hidden tabs
    checkHiddenTabErrors(form, activeTab, tabFieldMapping, tabLabels);
    
    // If validation failed, don't proceed (toast already shown by checkHiddenTabErrors)
    if (!isValid) {
      return;
    }

    // Form is valid, proceed with submission
    const values = form.getValues();
    await onSubmit(values);
  };
}

