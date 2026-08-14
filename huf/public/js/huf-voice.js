/**
 * HUF Voice Session Embed Bundle
 *
 * Framework-free, dependency-free JavaScript bundle for third-party websites
 * to mint voice sessions for HUF Agents using a publishable key.
 *
 * No live audio/WebSocket wiring — session minting only.
 *
 * Usage:
 *   const voiceClient = HufVoice.init({
 *     baseUrl: 'https://your-huf-site.com',
 *     publishableKey: 'pk_...',
 *     agent: 'agent-docname'
 *   });
 *
 *   voiceClient.startSession().then(session => {
 *     console.log('Session ready:', session);
 *   }).catch(err => {
 *     console.error('Failed to start session:', err.message);
 *   });
 */

(function (global) {
  'use strict';

  /**
   * Parse Frappe error response and extract user-friendly message
   * @param {unknown} errorData - Parsed JSON error response from Frappe
   * @returns {string} User-friendly error message
   */
  function extractFrappeErrorMessage(errorData) {
    if (!errorData || typeof errorData !== 'object') {
      return 'Unknown error occurred';
    }

    // Try _server_messages first (Frappe's structured error array)
    if (errorData._server_messages) {
      try {
        var messages = typeof errorData._server_messages === 'string'
          ? JSON.parse(errorData._server_messages)
          : errorData._server_messages;

        if (Array.isArray(messages) && messages.length > 0) {
          var firstMsg = messages[0];
          return (typeof firstMsg === 'object' && firstMsg.message)
            ? firstMsg.message
            : String(firstMsg);
        }
      } catch (e) {
        // Fall through to other options
      }
    }

    // Try message field
    if (typeof errorData.message === 'string') {
      return errorData.message;
    }

    // Try exception field
    if (typeof errorData.exception === 'string') {
      return errorData.exception;
    }

    // Try exc field
    if (typeof errorData.exc === 'string') {
      return errorData.exc;
    }

    return 'Unknown error occurred';
  }

  /**
   * Create an Error with Frappe error details
   * @param {unknown} responseBody - Parsed JSON response body
   * @returns {Error} Error with message from Frappe response
   */
  function createFrappeError(responseBody) {
    var message = extractFrappeErrorMessage(responseBody);
    var error = new Error(message);
    error.frappeResponse = responseBody;
    return error;
  }

  /**
   * Initialize HUF Voice session minter
   * @param {Object} config - Configuration object
   * @param {string} config.baseUrl - HUF site origin (e.g., 'https://mysite.example.com')
   * @param {string} config.publishableKey - Agent's publishable_key (starts with 'pk_')
   * @param {string} config.agent - Agent's docname
   * @returns {Object} Object with a startSession() method
   */
  function init(config) {
    if (!config || typeof config !== 'object') {
      throw new Error('HufVoice.init() requires a configuration object');
    }

    var baseUrl = config.baseUrl;
    var publishableKey = config.publishableKey;
    var agent = config.agent;

    if (typeof baseUrl !== 'string' || !baseUrl.length) {
      throw new Error('HufVoice.init() requires baseUrl (string)');
    }

    if (typeof publishableKey !== 'string' || !publishableKey.length) {
      throw new Error('HufVoice.init() requires publishableKey (string)');
    }

    if (typeof agent !== 'string' || !agent.length) {
      throw new Error('HufVoice.init() requires agent (string)');
    }

    // Normalize baseUrl: remove trailing slash
    var normalizedBaseUrl = baseUrl.replace(/\/$/, '');

    /**
     * Start a voice session
     *
     * No caller-supplied config: the backend always uses the Agent's own
     * saved voice configuration, never anything the browser sends. A
     * publishable key is public by design (it ships in this page's own
     * source), so accepting a config here would let anyone holding the key
     * point a session at an engine config of their choosing.
     * @returns {Promise<Object>} Promise resolving to session metadata from Frappe response
     */
    function startSession() {
      return new Promise(function (resolve, reject) {
        // Build request body
        var requestBody = {
          publishable_key: publishableKey,
          agent: agent
        };

        // Make POST request to Frappe whitelisted method
        fetch(normalizedBaseUrl + '/api/method/huf.ai.voice.api.start_public_session', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          credentials: 'omit',  // Do not send any cookies; must work for fully anonymous third-party visitor
          body: JSON.stringify(requestBody)
        })
          .then(function (response) {
            // Parse response body as JSON regardless of status
            return response.json().then(function (data) {
              return { response: response, data: data };
            });
          })
          .then(function (parsed) {
            var response = parsed.response;
            var data = parsed.data;

            // Handle non-2xx status
            if (!response.ok) {
              var errorMessage = extractFrappeErrorMessage(data);
              var error = new Error(errorMessage);
              error.frappeResponse = data;
              error.statusCode = response.status;
              reject(error);
              return;
            }

            // Unwrap Frappe's message wrapper: successful responses have { message: <actual-response> }
            var sessionData = data.message;
            if (sessionData === undefined || sessionData === null) {
              reject(new Error('Invalid response: missing message field'));
              return;
            }

            // Resolve with session metadata
            resolve(sessionData);
          })
          .catch(function (err) {
            // Network error or JSON parse error
            if (err instanceof Error) {
              reject(err);
            } else {
              reject(new Error('Request failed: ' + String(err)));
            }
          });
      });
    }

    return {
      startSession: startSession
    };
  }

  // Export to global scope
  global.HufVoice = {
    init: init
  };
})(typeof window !== 'undefined' ? window : global);
