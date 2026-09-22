/**
 * Classic Desk page for the "meeting-recorder" HUF App (Phase 4 of the
 * HufAppDeskPortalDelivery track).
 *
 * Coexistence, not replacement: this page does NOT replace the app's
 * `/huf` SPA launcher tile. It is a second, independent delivery surface
 * for the exact same underlying Agent ("Meeting Summary Agent"). See
 * doc/features/apps/delivery-portal-vs-desk.md ("Desk pages: coexist or
 * replace the SPA tile?") for the full rationale; short version: coexisting
 * is safer (no risk of breaking the existing SPA flow for any user relying
 * on it today), less disruptive (zero change to app_seeding/apps_loader.py's
 * existing sync behavior or the React SPA build), and reversible (this page
 * can be deleted without touching the SPA or the HUF App record at all) --
 * none of which hold if Desk delivery had to replace the tile app-by-app as
 * each one migrates.
 *
 * Boot pattern: unlike `/huf` (which boots once for the whole SPA via
 * www/huf.py:get_context), this page makes its own frappe.call() on
 * on_page_load, gated server-side by frappe.has_permission("Page", ...)
 * (see meeting_recorder.py:get_boot) -- a Desk page has no shared boot of
 * its own, so it must fetch and permission-check independently every time
 * it is shown.
 *
 * Chat UI: embeds Phase 3's huf.public.js.agent-chat-core module
 * (HufAgentChatCore) via frappe.require, per doc/reference/frappe-framework
 * /assets/asset-bundling.md's "lazy loading in /app" pattern. Vanilla JS
 * per doc/reference/frappe-framework/desk/page-api.md -- no concrete reason
 * surfaced during this build to reach for vue-inside-desk-page.md's heavier
 * pattern for a single scrollback + textbox chat UI.
 */
frappe.pages["meeting_recorder"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Meeting Recorder"),
		single_column: true,
	});

	page.main.html(
		'<div class="huf-desk-chat" style="max-width: 720px; margin: 0 auto;">' +
			'<div class="huf-desk-chat-status text-muted" style="padding: 12px 0;">' +
			__("Loading...") +
			"</div>" +
			'<div class="huf-desk-chat-messages" style="display:none; min-height: 300px; ' +
			'border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; ' +
			'margin-bottom: 12px; overflow-y: auto; max-height: 60vh;"></div>' +
			'<div class="huf-desk-chat-input" style="display:none;">' +
			'<div class="input-group">' +
			'<input type="text" class="form-control huf-desk-chat-text" placeholder="' +
			__("Type a message...") +
			'">' +
			'<span class="input-group-btn">' +
			'<button class="btn btn-primary huf-desk-chat-send">' +
			__("Send") +
			"</button>" +
			"</span>" +
			"</div>" +
			"</div>" +
			"</div>"
	);

	var $status = page.main.find(".huf-desk-chat-status");
	var $messages = page.main.find(".huf-desk-chat-messages");
	var $inputRow = page.main.find(".huf-desk-chat-input");
	var $text = page.main.find(".huf-desk-chat-text");
	var $send = page.main.find(".huf-desk-chat-send");

	function renderMessage(message) {
		var who = message.role === "user" ? __("You") : message.name || __("Agent");
		var $row = $(
			'<div class="huf-desk-chat-msg" style="margin-bottom: 8px;">' +
				'<strong class="huf-desk-chat-msg-who"></strong>' +
				'<div class="huf-desk-chat-msg-text" style="white-space: pre-wrap;"></div>' +
				"</div>"
		);
		$row.find(".huf-desk-chat-msg-who").text(who + ": ");
		$row.find(".huf-desk-chat-msg-text").text(message.text || (message.audioUrl ? __("[audio]") : ""));
		$messages.append($row);
		$messages.scrollTop($messages[0].scrollHeight);
	}

	// Per-page boot: frappe.call() gated server-side by
	// frappe.has_permission("Page", ...) inside get_boot (meeting_recorder.py).
	// A denied/disabled response throws frappe.PermissionError, which lands
	// in the error callback below rather than callback -- the chat UI is
	// never rendered in that case.
	frappe.call({
		method: "huf.page.meeting_recorder.meeting_recorder.get_boot",
		callback: function (r) {
			if (!r.message) {
				$status.text(__("This page is unavailable."));
				return;
			}
			var boot = r.message;
			page.set_title(boot.title || __("Meeting Recorder"));

			frappe.require("/assets/huf/js/agent-chat-core.js", function () {
				var chat = HufAgentChatCore.mount({
					agent: boot.agent,
					csrfToken: boot.csrf_token,
					onMessage: renderMessage,
					onLoading: function (isLoading) {
						$send.prop("disabled", !!isLoading);
					},
					onError: function (message) {
						frappe.show_alert({ message: message, indicator: "red" });
					},
				});

				page.__huf_chat = chat; // reserved for on_page_hide teardown

				$status.hide();
				$messages.show();
				$inputRow.show();

				function send() {
					var value = $text.val();
					if (!value) return;
					$text.val("");
					chat.sendText(value);
				}

				$send.on("click", send);
				$text.on("keydown", function (e) {
					if (e.which === 13) send();
				});
			});
		},
		error: function () {
			$status.text(__("You do not have permission to view this page, or it is unavailable."));
		},
	});
};

frappe.pages["meeting_recorder"].on_page_hide = function () {
	// HufAgentChatCore.destroy() is currently a documented no-op (see
	// agent-chat-core.js's module docstring) but is called unconditionally
	// here so this page does the right thing automatically if a future
	// version of the core ever needs real teardown (timers, listeners).
	var page = frappe.pages["meeting_recorder"] && frappe.pages["meeting_recorder"].page;
	if (page && page.__huf_chat && typeof page.__huf_chat.destroy === "function") {
		page.__huf_chat.destroy();
		page.__huf_chat = null;
	}
};
