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
 * Extract server messages from Frappe error response
 * @param error - The error object from Frappe API
 * @returns Array of server messages or null if none found
 */
export function extractFrappeServerMessages(error: any): FrappeServerMessage[] | null {
  try {
    let messagesString: string | null = null;

    // Check if error has _server_messages property
    if (error?._server_messages) {
      messagesString = error._server_messages;
    } else if (error?.response?._server_messages) {
      // Check if error.response exists (some SDKs wrap errors)
      messagesString = error.response._server_messages;
    } else if (error?.data?._server_messages) {
      // Check if error.data exists (another possible structure)
      messagesString = error.data._server_messages;
    }

    if (!messagesString) {
      return null;
    }

    // Parse the JSON string array
    let parsedMessages = JSON.parse(messagesString);
    
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
export function getFrappeErrorMessage(error: any): string {
  // If this is a wrapped error from createFrappeError, use the original error
  const originalError = error?.originalError;
  const errorToProcess = originalError || error;

  // Try to extract server messages first (from original error if available)
  const serverMessages = extractFrappeServerMessages(errorToProcess);
  if (serverMessages && serverMessages.length > 0) {
    // Return the first message (usually the most relevant)
    const message = serverMessages[0].message || serverMessages[0].title || 'An error occurred';
    // Remove HTML tags if present (e.g., <strong> tags)
    return message.replace(/<[^>]*>/g, '');
  }

  // Fallback to exception message
  if (errorToProcess?.exception) {
    // Try to extract a readable message from the exception
    const exceptionStr = String(errorToProcess.exception);
    // Remove common prefixes like "frappe.exceptions."
    return exceptionStr.replace(/^frappe\.exceptions\.\w+Error:\s*/, '').replace(/^\(.+?,\s*/, '').replace(/\)$/, '');
  }

  // If this is a wrapped Error object, use its message (which is already user-friendly)
  if (error?.message && error instanceof Error) {
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
export function createFrappeError(error: any, defaultMessage?: string): Error {
  const message = getFrappeErrorMessage(error) || defaultMessage || 'An error occurred';
  const customError = new Error(message);
  
  // Preserve original error for debugging
  (customError as any).originalError = error;
  (customError as any).serverMessages = extractFrappeServerMessages(error);
  (customError as any).exceptionType = error?.exc_type || error?.exception?.split('.')?.pop()?.split('(')?.[0];
  
  return customError;
}

/**
 * Handle Frappe API errors and throw user-friendly errors
 * @param error - The error object from Frappe API
 * @param context - Context for logging (e.g., "Error creating agent")
 * @throws Error with user-friendly message
 */
export function handleFrappeError(error: any, context?: string): never {
  // Log the full error for debugging
  if (context) {
    console.error(`${context}:`, error);
  } else {
    console.error('Frappe API error:', error);
  }

  // Throw user-friendly error
  throw createFrappeError(error, context);
}

