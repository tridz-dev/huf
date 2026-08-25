# Gateway Allow List: The Expiration Gap

When you set your Telegram Gateway to **Allow list**, you are telling the bot: *"Act like a strict security guard. Only let people in if they are on my approved list. Ignore everyone else."*

While this is great for security, there is a hidden "trap" in the current system that can cause your bot to silently ignore you, even when you think you are approved.

---

## The "Expiring Badge" Bug

Imagine you hire an employee and print them a permanent ID badge. But because of a software glitch, the printer accidentally prints "Expires in 60 minutes" on the back of the badge. An hour later, the security guard kicks them out of the building, even though they are an approved employee!

This is exactly what is happening in the Gateway system:
1. When you first message the bot to get a Pairing Code, the system creates a temporary 60-minute expiration timer. 
2. When the administrator approves you, the system is *supposed* to erase that timer to give you permanent access. 
3. **The Bug:** The system forgets to erase the timer! 
4. Exactly 60 minutes after you first messaged the bot, your access expires. Because the Gateway is in `Allow list` mode (strict security), it silently drops all your messages, making it look like the bot is completely broken.

---

## Proposed Fix

To solve this issue permanently, we need to modify the underlying document logic for the `Gateway Access Entry`.

**Target File:** `huf/doctype/gateway_access_entry/gateway_access_entry.py`

**The Change:** 
We will add an `on_update` or `before_save` python hook to the `GatewayAccessEntry` class. This hook will enforce a simple rule: 
> *If the state is being changed to `Approved`, automatically clear the `expires_at` field (set it to `None`).*

This ensures that whether a pairing code is approved via the chat interface, or manually approved by an administrator in the Frappe Desk UI, the 60-minute expiration timer is always erased, granting the user the permanent access they expect.
