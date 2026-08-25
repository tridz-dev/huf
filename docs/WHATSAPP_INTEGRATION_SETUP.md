# Bug Report: WhatsApp Missing from Integration Service

## Issue Explanation
When attempting to configure the WhatsApp Gateway in the `huf` application, the `whatsapp` service is not available in the dropdown when creating a new **Integration Settings** record. 

While the WhatsApp Gateway Adapter logic is fully implemented (`WhatsAppGatewayAdapter` in `huf/ai/gateway_adapters/whatsapp.py`), the service was accidentally omitted from the default seed data during installation. This prevents users from configuring their Meta credentials through the standard Frappe Desk UI without using the Hub Chat pairing workflow.

## Steps to Reproduce (Test Case)
1. Log in to Frappe Desk and navigate to the **Integration Settings** list (`/desk/integration-settings`).
2. Click **Add Integration Settings**.
3. Open the **Service** dropdown menu.
4. **Expected Result**: `whatsapp` should be an available option, which would reveal the credential fields (Phone Number ID, Access Token, Webhook Verify Token).
5. **Actual Result**: `whatsapp` is missing from the list, making it impossible to create the integration setting manually.

## Suggested Code Fix

To fix this, we need to add the `whatsapp` service configuration to the `register_integration_services()` function in `huf/install.py`. 

Add the following dictionary to the `services` list (around line 1065):

```python
{
    "service_name": "whatsapp",
    "category": "Communication",
    "description": "Meta WhatsApp Cloud API for messaging",
    "required_credentials": [
        {"key": "phone_number_id", "label": "Phone Number ID", "required": True},
        {"key": "access_token", "label": "Meta Permanent/System Access Token", "required": True},
        {"key": "webhook_verify_token", "label": "Webhook Verify Token", "required": True}
    ]
}
```

*(Note: The `app_secret` has been intentionally omitted from the required schema because it is an optional field for HMAC signature verification. Advanced users can still add it manually via the UI if desired.)*

Once this code change is merged, running `bench execute huf.install.register_integration_services` (or triggering `after_migrate`) will correctly seed the database, exposing the WhatsApp fields in the UI.
