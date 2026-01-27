frappe.ui.form.on("Agent Chat", {
    refresh(frm) {
        frm.disable_save();
        render_chat_ui(frm);
    },

    onload(frm) {
        frm.refresh_fields();
    }
});

function render_chat_ui(frm) {
    const wrapper = $(frm.fields_dict.chat_ui.wrapper);
    wrapper.css({
        "padding": "0",
        "margin": "0",
        "border": "none"
    });

    if (wrapper.find(".agent-chat-container").length === 0) {
        wrapper.html(`
        <div class="agent-chat-container" style="display:flex; flex-direction:column; height:70vh; background:#fff;">
         <!-- Agent Selector -->
            <div class="chat-agent-selector" style="padding:12px; border-bottom:1px solid #e5e7eb; background:#f9fafb;">
                <label style="margin-right:8px; font-weight:500;">Choose Agent:</label>
                <select class="agent-select" style="padding:6px 10px; border-radius:6px; border:1px solid #d1d5db;">
                <option></option>
                </select>
            </div> 
            
            <!-- Messages Area -->
            <div class="agent-chat-messages" style="flex:1; overflow:auto; padding:16px; background:#fff;"></div>
            
            <!-- Input Area -->
            <div class="chat-input-container" style="padding:16px; border-top:1px solid #e5e7eb; background:#f9fafb;">
                <div style="display:flex; gap:8px; align-items:flex-end;">
                    <textarea 
                        class="chat-input" 
                        placeholder="Type your message..." 
                        style="flex:1; resize:none; border:1px solid #d1d5db; border-radius:8px; padding:12px; font-size:14px; line-height:1.4; min-height:44px; max-height:120px; outline:none; transition:border-color 0.2s;"
                        rows="1"
                    ></textarea>
                    <input type="file" accept="audio/*" class="audio-file-input" style="display:none;" />
                    <button class="audio-upload-btn btn" title="Upload audio">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="17 8 12 3 7 8"/>
                            <line x1="12" y1="3" x2="12" y2="15"/>
                        </svg>
                    </button>
                    <button class="audio-record-btn btn" title="Record audio">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                            <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                        </svg>
                    </button>
                    <button class="chat-send btn btn-primary" style="border-radius:8px; padding:10px 20px; height:44px; display:flex; align-items:center; gap:4px;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                        </svg>
                    </button>
                </div>
                <div style="text-align:center; margin-top:8px;">
                    <small style="color:#9ca3af;">Press Enter to send, Shift+Enter for new line</small>
                </div>
            </div>
        </div>
        `);

        const agentSelect = wrapper.find(".agent-select");
        const messagesEl = wrapper.find(".agent-chat-messages");
        const textarea = wrapper.find(".chat-input");
        const sendBtn = wrapper.find(".chat-send");
        const audioInput = wrapper.find(".audio-file-input");
        const uploadBtn = wrapper.find(".audio-upload-btn");
        const recordBtn = wrapper.find(".audio-record-btn");
        let mediaRecorder = null;
        let chunks = [];

        uploadBtn.on("click", () => audioInput.click());
        audioInput.on("change", function (e) {
            const file = this.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function (evt) {
                const b64 = evt.target.result;
                sendAudioToServer(frm, b64, file.name);
            };
            reader.readAsDataURL(file);
        });

        recordBtn.on("click", async function () {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                frappe.msgprint("Recording is not supported in this browser.");
                return;
            }
            if (!mediaRecorder) {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
                mediaRecorder.onstop = () => {
                    const blob = new Blob(chunks, { type: "audio/webm" });
                    chunks = [];
                    const reader = new FileReader();
                    reader.onload = function (evt) {
                        const b64 = evt.target.result;
                        sendAudioToServer(frm, b64, `recording_${Date.now()}.webm`);
                    };
                    reader.readAsDataURL(blob);
                    stream.getTracks().forEach(t => t.stop());
                    mediaRecorder = null;
                };
                mediaRecorder.start();
                recordBtn.text("⏹ Stop");
                setTimeout(() => { if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop(); }, 1000 * 60 * 3);
            } else {
                mediaRecorder.stop();
                recordBtn.html(`<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                                </svg>`);
            }
        });

        function sendAudioToServer(frm, dataUrl, filename) {
            const messagesEl = $(frm.fields_dict.chat_ui.wrapper).find(".agent-chat-messages");
            append_message(messagesEl, "user", frappe.session.user, `(voice message: ${filename})`, new Date());

            frappe.call({
                method: "huf.ai.agent_chat.upload_audio_and_transcribe",
                args: {
                    docname: frm.doc.name,
                    filename: filename,
                    b64data: dataUrl,
                    agent: frm.doc.agent,
                    conversation: frm.doc.conversation
                },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        append_message(messagesEl, "user", frappe.session.user, r.message.transcript, new Date());

                        if (r.message.run && r.message.run.success) {
                            append_message(messagesEl, "agent", frm.doc.agent, r.message.run.response, new Date());
                            if (r.message.run.conversation_id && !frm.doc.conversation) {
                                frm.set_value("conversation", r.message.run.conversation_id);
                            }
                        }
                        scroll_to_bottom(messagesEl);
                    } else {
                        append_message(messagesEl, "system", "System", "Transcription failed: " + (r.message?.error || "Unknown"), new Date());
                    }
                }

            });
        }

        textarea.on("input", function () {
            this.style.height = "auto";
            this.style.height = Math.min(this.scrollHeight, 120) + "px";
        });

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Agent",
                fields: ["name", "agent_name"],
                filters: { allow_chat: 1, disabled: 0 }
            },
            callback(r) {
                if (r.message) {
                    r.message.forEach(agent => {
                        agentSelect.append(`<option value="${agent.name}">${agent.agent_name}</option>`);
                    });

                    if (frm.doc.agent) {
                        agentSelect.val(frm.doc.agent);
                    } else {
                        const first = agentSelect.find("option").first().val();
                        if (first) {
                            agentSelect.val(first);
                            frm.set_value("agent", first);
                        }
                    }
                }
            }
        });

        agentSelect.on("change", function () {
            const selectedAgent = $(this).val();
            frm.set_value("agent", selectedAgent);
        });

        // Load history
        load_history(frm, messagesEl);

        // Send on button
        sendBtn.on("click", () => send_message(frm, textarea, messagesEl));

        // Enter to send
        textarea.on("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send_message(frm, textarea, messagesEl);
            }
        });

        setTimeout(() => textarea.focus(), 100);
    }
}

function load_history(frm, messagesEl) {
    if (!frm.doc.conversation) {
        messagesEl.html(`
            <div style="display:flex; justify-content:center; align-items:center; height:100%; color:#6b7280;">
                <div style="text-align:center;">
                    <div style="font-size:16px; font-weight:500; margin-bottom:8px;">Start a conversation</div>
                    <div style="font-size:14px;">Ask me anything and I'll help you out!</div>
                </div>
            </div>
        `);
        return;
    }

    frappe.call({
        method: "huf.ai.agent_chat.get_history",
        args: { conversation_id: frm.doc.conversation },
        callback(r) {
            messagesEl.empty();
            if (r.message && r.message.length > 0) {
                r.message.forEach((m) => {
                    append_message(messagesEl, m.role, m.user, m.content, m.creation);
                });
                scroll_to_bottom(messagesEl);
            } else {
                messagesEl.html(`
                    <div style="display:flex; justify-content:center; align-items:center; height:100%; color:#6b7280;">
                        <div style="text-align:center;">
                            <div style="font-size:16px;">No messages yet</div>
                        </div>
                    </div>
                `);
            }
        }
    });
}

function send_message(frm, textarea, messagesEl) {
    const msg = textarea.val().trim();
    if (!msg) return;

    textarea.css("height", "44px");

    if (frm.is_new()) {
        frm.save().then(() => {
            do_send(frm, msg, textarea, messagesEl);
        });
    } else {
        do_send(frm, msg, textarea, messagesEl);
    }
}

function do_send(frm, msg, textarea, messagesEl) {
    const wrapper = $(frm.fields_dict.chat_ui.wrapper);
    const sendBtn = wrapper.find(".chat-send");
    const selectedAgent = wrapper.find(".agent-select").val() || frm.doc.agent;

    if (!sendBtn.data("original-icon")) {
        sendBtn.data("original-icon", sendBtn.html());
    }

    textarea.prop("disabled", true);
    sendBtn.prop("disabled", true);
    sendBtn.html(`
        <svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" 
             fill="none" viewBox="0 0 24 24" width="20" height="20">
          <circle class="opacity-25" cx="12" cy="12" r="10" 
                  stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" 
                d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z">
          </path>
        </svg>
    `);

    append_message(messagesEl, "user", frappe.session.user, msg, new Date());
    scroll_to_bottom(messagesEl);

    textarea.val("").css("height", "44px");

    // STREAMING IMPLEMENTATION
    const agentName = selectedAgent || frm.doc.agent;
    const streamUrl = `/huf/stream/${encodeURIComponent(agentName)}`;

    // Create specific ID for this message bubble
    const msgId = "msg-" + frappe.utils.get_random(6);
    // Append empty agent bubble first
    append_message(messagesEl, "agent", agentName, "", new Date(), msgId);
    const bubbleContent = messagesEl.find(`#${msgId} .chat-bubble-content`); // We need to target the content div inside the bubble

    // Helper to scroll
    const scroll = () => scroll_to_bottom(messagesEl);

    fetch(streamUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": frappe.csrf_token
        },
        body: JSON.stringify({
            prompt: msg,
            conversation_id: frm.doc.conversation
        })
    }).then(async response => {
        if (!response.ok) throw new Error("Network response was not ok");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // Keep incomplete line

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.type === 'delta') {
                            const text = data.content || '';
                            fullResponse += text;
                            // Update UI - for now just set text, Markdown rendering might be heavy per-chunk
                            // ideally use a streaming markdown parser or just append text
                            bubbleContent.html(frappe.markdown(fullResponse));
                            scroll();
                        } else if (data.type === 'tool_call') {
                            const toolName = data.tool_call?.function?.name || 'tool';
                            // Optional: indicate tool usage
                            // bubbleContent.append(`<div class="text-xs text-gray-500">🛠️ Using ${toolName}...</div>`);
                        } else if (data.type === 'complete') {
                            fullResponse = data.full_response || fullResponse;
                            bubbleContent.html(frappe.markdown(fullResponse));

                            if (data.conversation_id && !frm.doc.conversation) {
                                frm.set_value("conversation", data.conversation_id);
                            }
                            if (!frm.doc.agent && selectedAgent) {
                                frm.set_value("agent", selectedAgent);
                            }
                            scroll();
                        } else if (data.type === 'error') {
                            bubbleContent.append(`<div style="color:red; margin-top:8px;">Error: ${data.error}</div>`);
                        }
                    } catch (e) {
                        console.error("Error parsing stream chunk", e);
                    }
                }
            }
        }
    }).catch(err => {
        console.error("Stream error:", err);
        append_message(messagesEl, "system", "System", "Error: " + err.message, new Date());
    }).finally(() => {
        sendBtn.html(sendBtn.data("original-icon"));
        sendBtn.prop("disabled", false);
        textarea.prop("disabled", false);
        textarea.focus();
    });
}

function append_message(messagesEl, role, sender, content, ts, customId) {
    const isUser = role === "user";
    const isSystem = role === "system";

    const bubbleStyle = isUser ?
        "background:#f3f4f6; color:#374151;" :
        isSystem ?
            "background:#fee2e2; color:#dc2626; border:1px solid #fecaca;" :
            "background:#f3f4f6; color:#374151;";

    const align = isUser ? "flex-end" : "flex-start";
    const time = ts ? new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "";
    const displayName = isUser ? "You" : (isSystem ? "System" : sender);
    const msgId = customId || ("msg-" + frappe.utils.get_random(6));

    messagesEl.append(`
        <div style="display:flex; justify-content:${align}; margin-bottom:16px;">
            <div style="max-width:80%; position:relative;">

                <!-- Chat Bubble -->
                <div id="${msgId}" style="${bubbleStyle} padding:10px 14px; border-radius:12px; font-size:14px; line-height:1.5;">
                    <div class="chat-bubble-content">${frappe.markdown(content || "")}</div>
                    <button class="copy-msg-btn" data-target="${msgId}" 
                        style="position:absolute; top:6px; padding:6px; right:6px; border:none; background:none; cursor:pointer; color:black; display:none;"
                        title="Copy">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    </button>
                </div>

                <div style="margin-bottom:4px; font-size:12px; color:#6b7280; padding:0 8px;  text-align: right;">
                    <span>${displayName} • ${time}</span>
                </div>

            </div>
        </div>
    `);

    const bubble = messagesEl.find(`#${msgId}`);
    const copyBtn = bubble.find(".copy-msg-btn");

    bubble.on("mouseenter", () => copyBtn.show());
    bubble.on("mouseleave", () => copyBtn.hide());

    copyBtn.off("click").on("click", function () {
        const text = bubble.text().trim();
        navigator.clipboard.writeText(text).then(() => {
            frappe.show_alert({ message: "Message copied!", indicator: "green" });
        }).catch(() => {
            frappe.show_alert({ message: "Failed to copy", indicator: "red" });
        });
    });
}

function scroll_to_bottom(messagesEl) {
    messagesEl.scrollTop(messagesEl[0].scrollHeight);
}
