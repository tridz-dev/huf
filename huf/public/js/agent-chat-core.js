/**
 * agent-chat-core.js - framework-agnostic HUF agent chat/transport core.
 *
 * Extracted from huf/www/agent_chat.html (Phase 3 of the HufAppDeskPortalDelivery
 * track) so the message send/receive + streaming/polling transport is a single
 * reusable piece instead of a copy-paste fork per surface. Consumers so far / planned:
 *   - huf/www/agent_chat.html itself (retrofitted onto this module, voice UI)
 *   - Phase 2's per-app www/ portal template (huf.ai.app_portal_renderer)
 *   - Phase 4's classic Desk page.js (frappe.ui.Page, POS pattern)
 *
 * Design goals:
 *   - No global singleton state. Everything lives on the object `mount()` returns,
 *     so more than one instance can exist on a page (or a Desk page can create and
 *     destroy one per page-show).
 *   - No assumption about the surrounding DOM beyond a single container element and
 *     a small set of optional callback hooks -- it does not render bubbles, players,
 *     or a waveform itself. Callers own presentation; this module owns transport.
 *   - Works as a plain global (`window.HufAgentChatCore`) via a script tag, which is
 *     what a Desk page.js (loaded through frappe.require, not ES modules) needs --
 *     see doc/reference/frappe-framework/assets/asset-bundling.md ("Lazy loading in
 *     /app" via frappe.require). Also assigns `module.exports` when a CommonJS/ESM
 *     wrapper is present, for future bundled consumers.
 *
 * Usage:
 *   var chat = HufAgentChatCore.mount({
 *     agent: "Support Agent",              // required: HUF Agent name/label
 *     csrfToken: window.csrf_token,        // optional: falls back to the csrf_token cookie
 *     conversationId: null,                // optional: resume an existing conversation
 *     onMessage: function (message) {...}, // called for every new message (user + assistant)
 *     onLoading: function (loading) {...}, // called with true/false around each send
 *     onError: function (message) {...},   // called with a human-readable error string
 *   });
 *
 *   chat.sendText("hello");
 *   chat.sendAudio(blob);       // Blob, e.g. from MediaRecorder
 *   chat.refreshHistory();      // poll for new assistant Audio messages
 *   chat.reset();               // start a new conversation, clears local state
 *   chat.destroy();             // no-op today (no timers/listeners owned by the core
 *                                // itself) but reserved so callers have one thing to
 *                                // call unconditionally on teardown (Desk page hide,
 *                                // portal template unload) without caring whether a
 *                                // future version of this module ever needs cleanup.
 *
 * Every method returns a Promise where it makes a server call, so callers can chain
 * their own UI updates (e.g. re-render after `sendText` resolves) instead of relying
 * on the onMessage/onError hooks alone.
 */
(function (root, factory) {
	if (typeof module === "object" && module.exports) {
		module.exports = factory();
	} else {
		root.HufAgentChatCore = factory();
	}
})(typeof self !== "undefined" ? self : this, function () {
	"use strict";

	function getCsrfTokenFallback() {
		if (typeof window === "undefined") return "";
		if (window.csrf_token) return window.csrf_token;
		var cookie = document.cookie.split(";").find(function (c) {
			return c.trim().indexOf("csrf_token=") === 0;
		});
		return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
	}

	function noop() {}

	/**
	 * Create a chat core instance. `config`:
	 *   agent           (string, required)  HUF Agent name shown in create_conversation.
	 *   channel         (string, default "Chat") passed to create_conversation.
	 *   conversationId  (string, optional)  resume an existing conversation.
	 *   csrfToken       (string, optional)  overrides the cookie/window.csrf_token lookup.
	 *   endpoints       (object, optional)  override any of the four whitelisted method
	 *                   paths this core calls, for a consumer pointed at a fork:
	 *                     createConversation, sendMessage, uploadAudio, listMessages
	 *   historyLimit    (number, default 5) page size for refreshHistory's Agent Message query.
	 *   onMessage(message)   called once per new message: {role, kind, text, audioUrl, name, timeLabel}
	 *   onLoading(isLoading) called around every network round-trip
	 *   onError(text)        called with a human-readable string on failure
	 */
	function mount(config) {
		config = config || {};
		if (!config.agent) throw new Error("HufAgentChatCore.mount: config.agent is required");

		var endpoints = Object.assign(
			{
				createConversation: "huf.ai.agent_chat.create_conversation",
				sendMessage: "huf.ai.agent_chat.send_message_to_conversation",
				uploadAudio: "huf.ai.agent_chat.upload_audio_and_transcribe_web",
				listMessages: "/api/resource/Agent Message",
			},
			config.endpoints || {}
		);

		var onMessage = typeof config.onMessage === "function" ? config.onMessage : noop;
		var onLoading = typeof config.onLoading === "function" ? config.onLoading : noop;
		var onError = typeof config.onError === "function" ? config.onError : noop;
		var historyLimit = config.historyLimit || 5;

		var state = {
			agent: config.agent,
			channel: config.channel || "Chat",
			conversationId: config.conversationId || null,
			seenMessageIds: new Set(),
			csrfToken: config.csrfToken || null,
		};

		function csrfToken() {
			return state.csrfToken || getCsrfTokenFallback();
		}

		function callMethod(method, args) {
			return fetch("/api/method/" + method, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-Frappe-CSRF-Token": csrfToken(),
				},
				body: JSON.stringify(args || {}),
			}).then(function (res) {
				if (!res.ok) {
					return res.text().then(function (text) {
						throw new Error(text || "Request failed");
					});
				}
				return res.json().then(function (payload) {
					return payload.message;
				});
			});
		}

		function ensureConversation() {
			if (state.conversationId) return Promise.resolve(state.conversationId);
			return callMethod(endpoints.createConversation, {
				agent: state.agent,
				channel: state.channel,
			}).then(function (payload) {
				state.conversationId = payload.conversation_id;
				return state.conversationId;
			});
		}

		function refreshHistory() {
			if (!state.conversationId) return Promise.resolve([]);
			var params = new URLSearchParams({
				fields: JSON.stringify([
					"name",
					"conversation",
					"role",
					"kind",
					"is_agent_message",
					"generated_audio",
					"voice_message",
					"creation",
				]),
				filters: JSON.stringify([
					["Agent Message", "conversation", "=", state.conversationId],
					["Agent Message", "kind", "=", "Audio"],
					["Agent Message", "is_agent_message", "=", 1],
				]),
				order_by: "creation desc",
				limit_page_length: String(historyLimit),
			});
			return fetch(endpoints.listMessages + "?" + params, {
				method: "GET",
				headers: { "X-Frappe-CSRF-Token": csrfToken() },
			})
				.then(function (res) {
					if (!res.ok) throw new Error("Failed to load history");
					return res.json();
				})
				.then(function (data) {
					var docs = Array.isArray(data.data) ? data.data : [];
					var fresh = [];
					docs
						.slice()
						.reverse()
						.forEach(function (m) {
							if (state.seenMessageIds.has(m.name)) return;
							var audioUrl = m.voice_message || m.generated_audio || null;
							if (!audioUrl) return;
							state.seenMessageIds.add(m.name);
							var message = {
								role: "assistant",
								kind: "audio",
								name: m.name,
								audioUrl: audioUrl,
								timeLabel: new Date(m.creation).toLocaleTimeString([], {
									hour: "2-digit",
									minute: "2-digit",
								}),
							};
							fresh.push(message);
							onMessage(message);
						});
					return fresh;
				})
				.catch(function (e) {
					onError("Failed to load history");
					throw e;
				});
		}

		function sendText(text) {
			if (!text || !text.trim()) return Promise.resolve(null);
			onLoading(true);
			var userMessage = {
				role: "user",
				kind: "text",
				text: text,
				timeLabel: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			};
			onMessage(userMessage);
			return ensureConversation()
				.then(function (conversationId) {
					return callMethod(endpoints.sendMessage, {
						conversation: conversationId,
						message: text,
					});
				})
				.then(function (result) {
					return refreshHistoryAfterDelay();
				})
				.catch(function (e) {
					onError("Failed to send message");
					throw e;
				})
				.finally(function () {
					onLoading(false);
				});
		}

		function sendAudio(blob) {
			onLoading(true);
			var userMessage = {
				role: "user",
				kind: "audio",
				audioUrl: typeof URL !== "undefined" && URL.createObjectURL ? URL.createObjectURL(blob) : null,
				timeLabel: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
			};
			onMessage(userMessage);

			return ensureConversation()
				.then(function (conversationId) {
					return new Promise(function (resolve, reject) {
						var reader = new FileReader();
						reader.onload = function (evt) {
							var dataUrl = evt.target && evt.target.result;
							if (!dataUrl || typeof dataUrl !== "string") {
								reject(new Error("Failed to read audio"));
								return;
							}
							callMethod(endpoints.uploadAudio, {
								filename: "recording_" + Date.now() + ".webm",
								b64data: dataUrl,
								agent: state.agent,
								conversation: conversationId,
							})
								.then(function (result) {
									if (!result || !result.success) {
										reject(new Error((result && result.error) || "Transcription failed"));
										return;
									}
									if (!state.conversationId && result.conversation_id) {
										state.conversationId = result.conversation_id;
									}
									resolve(result);
								})
								.catch(reject);
						};
						reader.onerror = function () {
							reject(new Error("Failed to read audio"));
						};
						reader.readAsDataURL(blob);
					});
				})
				.then(function (result) {
					return refreshHistoryAfterDelay().then(function () {
						return result;
					});
				})
				.catch(function (e) {
					onError("Failed to send audio");
					throw e;
				})
				.finally(function () {
					onLoading(false);
				});
		}

		function refreshHistoryAfterDelay() {
			// The agent's reply is generated asynchronously server-side; give it a
			// moment before polling, same delay agent_chat.html always used.
			return new Promise(function (resolve) {
				setTimeout(function () {
					refreshHistory().then(resolve, resolve);
				}, 2000);
			});
		}

		function reset() {
			state.conversationId = null;
			state.seenMessageIds = new Set();
		}

		function destroy() {
			// Reserved for future cleanup (no timers/listeners are currently owned
			// by the core itself); see module doc comment above.
		}

		return {
			get conversationId() {
				return state.conversationId;
			},
			sendText: sendText,
			sendAudio: sendAudio,
			refreshHistory: refreshHistory,
			ensureConversation: ensureConversation,
			reset: reset,
			destroy: destroy,
		};
	}

	return { mount: mount };
});
