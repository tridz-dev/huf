frappe.ui.form.on("Agent Chat", {
    refresh(frm) {
        frm.disable_save();
        render_chat_ui(frm);
    },

    onload(frm) {
        frm.refresh_fields();
    }
});

// Add CSS animations for spinners and typing indicators
if (!document.getElementById("agent-chat-animations")) {
    const style = document.createElement("style");
    style.id = "agent-chat-animations";
    style.textContent = `
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
        }
        .animate-spin {
            animation: spin 1s linear infinite;
        }
    `;
    document.head.appendChild(style);
}

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
                method: "agentflo.ai.agent_chat.upload_audio_and_transcribe",
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
        sendBtn.on("click", () => send_message_stream(frm, textarea, messagesEl));

        // Enter to send
        textarea.on("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send_message_stream(frm, textarea, messagesEl);
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
        method: "agentflo.ai.agent_chat.get_history",
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
    // Use streaming version by default
    send_message_stream(frm, msg, textarea, messagesEl);
}

function send_message_stream(frm, textarea, messagesEl) {
    const msg = typeof textarea === "string" ? textarea : textarea.val().trim();
    if (!msg) return;

    const wrapper = $(frm.fields_dict.chat_ui.wrapper);
    const sendBtn = wrapper.find(".chat-send");
    const selectedAgent = wrapper.find(".agent-select").val() || frm.doc.agent;

    if (!sendBtn.data("original-icon")) {
        sendBtn.data("original-icon", sendBtn.html());
    }

    if (typeof textarea !== "string") {
        textarea.prop("disabled", true);
        textarea.val("").css("height", "44px");
    }
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

    // Append user message
    append_message(messagesEl, "user", frappe.session.user, msg, new Date());
    scroll_to_bottom(messagesEl);

    // Create placeholder for streaming agent message
    const streamingMsgId = "streaming-" + Date.now();
    append_message(messagesEl, "agent", selectedAgent || frm.doc.agent, "", new Date(), streamingMsgId);
    const streamingEl = messagesEl.find(`#${streamingMsgId}`);
    streamingEl.addClass("streaming-message");
    
    // Track state
    let accumulatedContent = "";
    let currentToolCalls = {}; // Track tool calls by name
    
    // Build SSE URL
    const baseUrl = frappe.settings.app_url || window.location.origin;
    const apiUrl = `${baseUrl}/api/method/agentflo.ai.agent_chat.send_message_stream`;
    const params = new URLSearchParams({
        docname: frm.doc.name,
        message: msg,
        agent: selectedAgent || ""
    });
    
    // Note: EventSource doesn't support POST, so we need to use GET
    // For security, ensure the endpoint validates user permissions
    const eventSource = new EventSource(`${apiUrl}?${params.toString()}`);
    
    // Handle agent thinking state
    eventSource.addEventListener("agent_thinking", (e) => {
        const data = JSON.parse(e.data);
        update_message_status(streamingMsgId, "thinking");
    });
    
    // Handle tool call start
    eventSource.addEventListener("tool_call_start", (e) => {
        const data = JSON.parse(e.data);
        const toolName = data.tool;
        const toolArgs = data.args || {};
        
        // Create tool call indicator
        const toolCallId = `tool-${toolName}-${Date.now()}`;
        currentToolCalls[toolName] = toolCallId;
        
        const toolIndicator = render_tool_call(toolName, "running", toolArgs, null, toolCallId);
        streamingEl.before(toolIndicator);
        scroll_to_bottom(messagesEl);
    });
    
    // Handle tool call complete
    eventSource.addEventListener("tool_call_complete", (e) => {
        const data = JSON.parse(e.data);
        const toolName = data.tool;
        const result = data.result;
        
        const toolCallId = currentToolCalls[toolName];
        if (toolCallId) {
            update_tool_status(toolCallId, "complete", result);
        }
        scroll_to_bottom(messagesEl);
    });
    
    // Handle tool call error
    eventSource.addEventListener("tool_call_error", (e) => {
        const data = JSON.parse(e.data);
        const toolName = data.tool;
        const error = data.error;
        
        const toolCallId = currentToolCalls[toolName];
        if (toolCallId) {
            update_tool_status(toolCallId, "error", error);
        }
        scroll_to_bottom(messagesEl);
    });
    
    // Handle content chunks
    eventSource.addEventListener("content_chunk", (e) => {
        const data = JSON.parse(e.data);
        accumulatedContent += data.content;
        update_streaming_message(streamingMsgId, accumulatedContent);
        scroll_to_bottom(messagesEl);
    });
    
    // Handle response complete
    eventSource.addEventListener("response_complete", (e) => {
        const data = JSON.parse(e.data);
        finalize_message(streamingMsgId, data.response || accumulatedContent);
        
        if (data.conversation_id && !frm.doc.conversation) {
            frm.set_value("conversation", data.conversation_id);
        }
        if (!frm.doc.agent && selectedAgent) {
            frm.set_value("agent", selectedAgent);
        }
        
        eventSource.close();
        reset_ui();
    });
    
    // Handle errors
    eventSource.addEventListener("error", (e) => {
        const data = JSON.parse(e.data);
        show_error(streamingMsgId, data.error || "An error occurred");
        eventSource.close();
        reset_ui();
    });
    
    // Handle connection errors
    eventSource.onerror = (error) => {
        console.error("SSE connection error:", error);
        if (eventSource.readyState === EventSource.CLOSED) {
            show_error(streamingMsgId, "Connection closed. Please try again.");
            reset_ui();
        }
    };
    
    function reset_ui() {
        sendBtn.html(sendBtn.data("original-icon"));
        sendBtn.prop("disabled", false);
        if (typeof textarea !== "string") {
            textarea.prop("disabled", false);
            textarea.focus();
        }
    }
}

function append_message(messagesEl, role, sender, content, ts, msgId = null) {
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
    if (!msgId) {
        msgId = "msg-" + frappe.utils.get_random(6);
    }

    messagesEl.append(`
        <div style="display:flex; justify-content:${align}; margin-bottom:16px;">
            <div style="max-width:80%; position:relative;">

                <!-- Chat Bubble -->
                <div id="${msgId}" style="${bubbleStyle} padding:10px 14px; border-radius:12px; font-size:14px; line-height:1.5; min-height:20px;">
                    ${frappe.markdown(content || "")}
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

function render_tool_call(toolName, status, args, result, toolCallId) {
    const statusColors = {
        "running": "#3b82f6",
        "complete": "#10b981",
        "error": "#ef4444"
    };
    const statusIcons = {
        "running": "⚙️",
        "complete": "✓",
        "error": "✗"
    };
    
    const color = statusColors[status] || "#6b7280";
    const icon = statusIcons[status] || "•";
    
    let argsDisplay = "";
    if (args && Object.keys(args).length > 0) {
        argsDisplay = `<div style="margin-top:8px; padding:8px; background:#f9fafb; border-radius:6px; font-size:12px; color:#6b7280;">
            <strong>Arguments:</strong><br>
            <pre style="margin:4px 0 0 0; white-space:pre-wrap; word-break:break-word;">${JSON.stringify(args, null, 2)}</pre>
        </div>`;
    }
    
    let resultDisplay = "";
    if (result) {
        const resultStr = typeof result === "string" ? result : JSON.stringify(result, null, 2);
        resultDisplay = `<div style="margin-top:8px; padding:8px; background:#f0fdf4; border-radius:6px; font-size:12px; color:#166534;">
            <strong>Result:</strong><br>
            <pre style="margin:4px 0 0 0; white-space:pre-wrap; word-break:break-word; max-height:200px; overflow-y:auto;">${frappe.utils.escape_html(resultStr)}</pre>
        </div>`;
    }
    
    const spinner = status === "running" ? `
        <span class="tool-spinner" style="display:inline-block; margin-left:8px; width:12px; height:12px; border:2px solid ${color}; border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite;"></span>
    ` : "";
    
    return `
        <div id="${toolCallId}" class="tool-call-indicator" style="margin-bottom:12px; padding:12px; background:#fff; border:1px solid #e5e7eb; border-left:3px solid ${color}; border-radius:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:16px;">${icon}</span>
                <span style="font-weight:500; color:#374151;">${frappe.utils.escape_html(toolName)}</span>
                <span style="padding:2px 8px; background:${color}20; color:${color}; border-radius:4px; font-size:11px; font-weight:500; text-transform:uppercase;">${status}</span>
                ${spinner}
            </div>
            ${argsDisplay}
            ${resultDisplay}
        </div>
    `;
}

function update_tool_status(toolCallId, status, result) {
    const toolEl = $(`#${toolCallId}`);
    if (!toolEl.length) return;
    
    const statusColors = {
        "running": "#3b82f6",
        "complete": "#10b981",
        "error": "#ef4444"
    };
    const statusIcons = {
        "running": "⚙️",
        "complete": "✓",
        "error": "✗"
    };
    
    const color = statusColors[status] || "#6b7280";
    const icon = statusIcons[status] || "•";
    
    // Update status badge
    toolEl.find(".tool-status-badge").remove();
    toolEl.find(".tool-spinner").remove();
    
    const header = toolEl.find("> div:first-child");
    header.append(`<span style="padding:2px 8px; background:${color}20; color:${color}; border-radius:4px; font-size:11px; font-weight:500; text-transform:uppercase;">${status}</span>`);
    header.find("span:first-child").text(icon);
    
    // Update border color
    toolEl.css("border-left-color", color);
    
    // Add result if provided
    if (result && !toolEl.find(".tool-result").length) {
        const resultStr = typeof result === "string" ? result : JSON.stringify(result, null, 2);
        toolEl.append(`<div class="tool-result" style="margin-top:8px; padding:8px; background:#f0fdf4; border-radius:6px; font-size:12px; color:#166534;">
            <strong>Result:</strong><br>
            <pre style="margin:4px 0 0 0; white-space:pre-wrap; word-break:break-word; max-height:200px; overflow-y:auto;">${frappe.utils.escape_html(resultStr)}</pre>
        </div>`);
    }
}

function update_streaming_message(msgId, content) {
    const msgEl = $(`#${msgId}`);
    if (!msgEl.length) return;
    
    msgEl.find(".message-content").remove();
    msgEl.html(frappe.markdown(content || ""));
    
    // Re-add copy button if it was there
    if (!msgEl.find(".copy-msg-btn").length) {
        msgEl.append(`
            <button class="copy-msg-btn" data-target="${msgId}" 
                style="position:absolute; top:6px; padding:6px; right:6px; border:none; background:none; cursor:pointer; color:black; display:none;"
                title="Copy">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
        `);
        
        const copyBtn = msgEl.find(".copy-msg-btn");
        msgEl.on("mouseenter", () => copyBtn.show());
        msgEl.on("mouseleave", () => copyBtn.hide());
        
        copyBtn.off("click").on("click", function () {
            const text = msgEl.text().trim();
            navigator.clipboard.writeText(text).then(() => {
                frappe.show_alert({ message: "Message copied!", indicator: "green" });
            }).catch(() => {
                frappe.show_alert({ message: "Failed to copy", indicator: "red" });
            });
        });
    }
    
    // Add typing indicator
    if (!msgEl.find(".typing-indicator").length && content) {
        msgEl.append(`<span class="typing-indicator" style="display:inline-block; margin-left:4px; width:8px; height:16px; background:#6b7280; animation:blink 1s infinite;"></span>`);
    }
}

function finalize_message(msgId, content) {
    const msgEl = $(`#${msgId}`);
    if (!msgEl.length) return;
    
    msgEl.removeClass("streaming-message");
    msgEl.addClass("complete-message");
    msgEl.find(".typing-indicator").remove();
    
    // Update with final content
    update_streaming_message(msgId, content);
}

function update_message_status(msgId, status) {
    const msgEl = $(`#${msgId}`);
    if (!msgEl.length) return;
    
    if (status === "thinking") {
        if (!msgEl.find(".thinking-indicator").length) {
            msgEl.append(`<div class="thinking-indicator" style="display:flex; align-items:center; gap:8px; color:#6b7280; font-size:12px; margin-top:8px;">
                <span class="spinner" style="display:inline-block; width:12px; height:12px; border:2px solid #6b7280; border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite;"></span>
                <span>Agent is thinking...</span>
            </div>`);
        }
    } else {
        msgEl.find(".thinking-indicator").remove();
    }
}

function show_error(msgId, error) {
    const msgEl = $(`#${msgId}`);
    if (!msgEl.length) return;
    
    msgEl.css({
        "background": "#fee2e2",
        "color": "#dc2626",
        "border": "1px solid #fecaca"
    });
    msgEl.html(`<strong>Error:</strong> ${frappe.utils.escape_html(error)}`);
}

function scroll_to_bottom(messagesEl) {
    messagesEl.scrollTop(messagesEl[0].scrollHeight);
}
