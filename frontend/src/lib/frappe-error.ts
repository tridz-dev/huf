/**
 * Frappe API Error Handler
 * Extracts user-friendly error messages from Frappe API error responses
 */

export interface FrappeServerMessage {
  message: string;
  title?: string;
  indicator?: string;
}

export interface FrappeErrorResponse {
  exception?: string;
  exc_type?: string;
  exc?: string;
  _server_messages?: string; // JSON string array of server messages
}

/**
 * Loose shape of a Frappe API error object.
 * Real payloads vary (axios wrappers, SDK errors, plain objects), so all fields are optional.
 */
interface FrappeErrorShape {
  _server_messages?: string;
  response?: { _server_messages?: string };
  data?: { _server_messages?: string };
  exception?: string;
  exc_type?: string;
  message?: string;
  originalError?: unknown;
}

/** Error augmented by createFrappeError with the original Frappe error details */
export interface FrappeError extends Error {
  originalError?: unknown;
  serverMessages?: FrappeServerMessage[] | null;
  exceptionType?: string;
}

/**
 * Extract server messages from Frappe error response
 * @param error - The error object from Frappe API
 * @returns Array of server messages or null if none found
 */
export function extractFrappeServerMessages(error: unknown): FrappeServerMessage[] | null {
  const err = error as FrappeErrorShape | null | undefined;
  try {
    let messagesString: string | null = null;

    // Check if error has _server_messages property
    if (err?._server_messages) {
      messagesString = err._server_messages;
    } else if (err?.response?._server_messages) {
      // Check if error.response exists (some SDKs wrap errors)
      messagesString = err.response._server_messages;
    } else if (err?.data?._server_messages) {
      // Check if error.data exists (another possible structure)
      messagesString = err.data._server_messages;
    }

    if (!messagesString) {
      return null;
    }

    // Parse the JSON string array
    const parsedMessages = JSON.parse(messagesString);
    
    // Handle case where parsedMessages might be an array of JSON strings
    if (Array.isArray(parsedMessages)) {
      return parsedMessages.map((msg) => {
        // If the message is a string, try to parse it as JSON
        if (typeof msg === 'string') {
          try {
            return JSON.parse(msg) as FrappeServerMessage;
          } catch {
            // If parsing fails, return as is (might be a plain string message)
            return { message: msg } as FrappeServerMessage;
          }
        }
        // If already an object, return as is
        return msg as FrappeServerMessage;
      });
    }

    // If it's a single object instead of array, wrap it
    if (parsedMessages && typeof parsedMessages === 'object') {
      return [parsedMessages as FrappeServerMessage];
    }

    return null;
  } catch (parseError) {
    console.error('Error parsing Frappe server messages:', parseError);
    return null;
  }
}

/**
 * Get the primary error message from Frappe error
 * @param error - The error object from Frappe API (can be original or wrapped Error)
 * @returns User-friendly error message string
 */
export function getFrappeErrorMessage(error: unknown): string {
  const err = error as FrappeErrorShape | null | undefined;
  // If this is a wrapped error from createFrappeError, use the original error
  const originalError = err?.originalError;
  const errorToProcess = (originalError || err) as FrappeErrorShape | null | undefined;

  // Try to extract server messages first (from original error if available)
  const serverMessages = extractFrappeServerMessages(errorToProcess);
  if (serverMessages && serverMessages.length > 0) {
    // Return the first message (usually the most relevant)
    const message = serverMessages[0].message || serverMessages[0].title || 'An error occurred';
    // Strip HTML tags and decode basic HTML entities safely without DOMParser parseFromString sinks
    return (
      message
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
        .replace(/<[^>]+>/g, '')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .trim() || 'An error occurred'
    );
  }

  // Fallback to exception message
  if (errorToProcess?.exception) {
    // Try to extract a readable message from the exception
    const exceptionStr = String(errorToProcess.exception);
    // Remove common prefixes like "frappe.exceptions."
    return exceptionStr.replace(/^frappe\.exceptions\.\w+Error:\s*/, '').replace(/^\(.+?,\s*/, '').replace(/\)$/, '');
  }

  // If this is a wrapped Error object, use its message (which is already user-friendly)
  if (error instanceof Error && error.message) {
    return error.message;
  }

  // Fallback to error message property
  if (errorToProcess?.message) {
    return errorToProcess.message;
  }

  // Fallback to string representation
  if (typeof error === 'string') {
    return error;
  }

  // Final fallback
  return 'An unexpected error occurred. Please try again.';
}

/**
 * Create a user-friendly error from Frappe API error
 * @param error - The error object from Frappe API
 * @param defaultMessage - Default message if error cannot be parsed
 * @returns Error object with user-friendly message
 */
export function createFrappeError(error: unknown, defaultMessage?: string): Error {
  const message = getFrappeErrorMessage(error) || defaultMessage || 'An error occurred';
  const customError = new Error(message) as FrappeError;
  const err = error as FrappeErrorShape | null | undefined;

  // Preserve original error for debugging
  customError.originalError = error;
  customError.serverMessages = extractFrappeServerMessages(error);
  customError.exceptionType = err?.exc_type || err?.exception?.split('.')?.pop()?.split('(')?.[0];

  return customError;
}

/**
 * Handle Frappe API errors and throw user-friendly errors
 * @param error - The error object from Frappe API
 * @param context - Context for logging (e.g., "Error creating agent")
 * @throws Error with user-friendly message
 */
export function handleFrappeError(error: unknown, context?: string): never {
  // Log the full error for debugging
  if (context) {
    console.error('Frappe API error context:', context, error);
  } else {
    console.error('Frappe API error:', error);
  }

  // Throw user-friendly error
  throw createFrappeError(error, context);
}
