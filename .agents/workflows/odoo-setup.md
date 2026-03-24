# Odoo Integration Workflow

This workflow describes how to set up and verify a new Odoo connection.

1.  **Initialize Connection**:
    - Create a new `Odoo Connection` document in HUF.
    - Provide the URL, Database, Username, and Password.
    - Click **Test Connection** to verify settings and protocol auto-detection.

2.  **Introspect Schema**:
    - Click **Discover Schema** on the connection document.
    - This triggers a background job to fetch all models and fields.
    - Verification: Check the `Odoo Schema Cache` list to see imported data.

3.  **Configure Triggers**:
    - **Webhooks**: Configure Odoo `base.automation` to send signals to the HUF webhook URL with the `webhook_key`.
    - **Polling**: Automated background job runs every minute if webhooks are not available.

4.  **Deploy Agent**:
    - Assign an Agent (e.g., "Odoo CRM Assistant") to the connection.
    - Test via the `Agent Console` or `Agent Chat`.
