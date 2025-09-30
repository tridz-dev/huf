frappe.ui.form.on("Agent Chat", {
    refresh(frm) {
        frm.disable_save();
        
        render_chat_ui(frm);
    },
    
    onload(frm) {
        // Hide unnecessary fields for cleaner UI
        frm.get_field("title").df.hidden = 1;
        frm.get_field("conversation").df.hidden = 1;
        frm.refresh_fields();
    }
});

function render_chat_ui(frm) {
    const wrapper = $(frm.fields_dict.chat_ui.wrapper);
    
    // Clear any existing content and remove padding
    wrapper.css({
        "padding": "0",
        "margin": "0",
        "border": "none"
    });

    if (wrapper.find(".agent-chat-container").length === 0) {
        wrapper.html(`
        <div class="agent-chat-container" style="display:flex; flex-direction:column; height:70vh; background:#fff;">
            <!-- Chat Header -->
            <div class="chat-header" style="padding:12px 16px; border-bottom:1px solid #e5e7eb; background:#f8fafc;">
                <div style="display:flex; align-items:center; justify-content:space-between;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <div style="width:8px; height:8px; border-radius:50%; background:#10b981;"></div>
                        <strong style="color:#374151;">${frm.doc.agent || 'AI Assistant'}</strong>
                    </div>
                    ${frm.doc.conversation ? `<small style="color:#6b7280;">${frm.doc.conversation}</small>` : ''}
                </div>
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

        const messagesEl = wrapper.find(".agent-chat-messages");
        const textarea = wrapper.find(".chat-input");
        const sendBtn = wrapper.find(".chat-send");

        // Auto-resize textarea
        textarea.on("input", function() {
            this.style.height = "auto";
            this.style.height = Math.min(this.scrollHeight, 120) + "px";
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

        // Focus on input
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

    // Reset textarea height
    textarea.css("height", "44px");

    // Ensure doc is saved first
    if (frm.is_new()) {
        frm.save().then(() => {
            do_send(frm, msg, textarea, messagesEl);
        });
    } else {
        do_send(frm, msg, textarea, messagesEl);
    }
}

function do_send(frm, msg, textarea, messagesEl) {
    // Remove empty state if present
    if (messagesEl.find(".empty-state").length) {
        messagesEl.empty();
    }

    append_message(messagesEl, "user", frappe.session.user, msg, new Date());
    scroll_to_bottom(messagesEl);
    textarea.val("");

    frappe.call({
        method: "agentflo.ai.agent_chat.send_message",
        args: { docname: frm.doc.name, message: msg },
        freeze: true,
        freeze_message: "Thinking...",
        callback(r) {
            if (r.message && r.message.success) {
                append_message(messagesEl, "agent", frm.doc.agent, r.message.response, new Date());
                if (r.message.conversation_id && !frm.doc.conversation) {
                    frm.set_value("conversation", r.message.conversation_id);
                }
                scroll_to_bottom(messagesEl);
            } else {
                append_message(messagesEl, "system", "System", "Error: " + (r.message?.error || "Unknown"), new Date());
            }
        }
    });
}

function append_message(messagesEl, role, sender, content, ts) {
    const isUser = role === "user";
    const isSystem = role === "system";
    
    const bubbleStyle = isUser ? 
        "background:#3b82f6; color:white;" : 
        isSystem ? 
        "background:#fee2e2; color:#dc2626; border:1px solid #fecaca;" : 
        "background:#f3f4f6; color:#374151;";
    
    const align = isUser ? "flex-end" : "flex-start";
    const time = ts ? new Date(ts).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : "";
    const displayName = isUser ? "You" : (isSystem ? "System" : sender);

    messagesEl.append(`
        <div style="display:flex; justify-content:${align}; margin-bottom:16px;">
            <div style="max-width:80%;">
                <div style="${bubbleStyle} padding:10px 14px; border-radius:12px; font-size:14px; line-height:1.5;">
                    ${frappe.utils.escape_html(content)}
                </div>
                <div style="margin-bottom:4px; font-size:12px; color:#6b7280; padding:0 8px;  text-align: right;">
                    ${displayName} • ${time}
                </div>
                
            </div>
        </div>
    `);
}

function scroll_to_bottom(messagesEl) {
    messagesEl.scrollTop(messagesEl[0].scrollHeight);
}