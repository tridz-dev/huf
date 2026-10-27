# Telegram web access: launch page

`/tg_open` is a static page that turns a Telegram Mini App tap into a signed-in Huf desk session. It reads
`Telegram.WebApp.initData`, posts it with the gateway name to `huf.ai.telegram_web_access.exchange`, and on
success navigates to the returned relative path. The session cookie is set by that response.

## Building the URL

```python
from huf.ai.telegram_web_access_url import web_access_url

web_access_url("my-gateway")                                 # https://<public>/tg_open?gw=my-gateway
web_access_url("my-gateway", "/app/query-report/Sales Run")  # adds &to=%2Fapp%2Fquery-report%2FSales+Run
```

Both values are URL-encoded; the base comes from `telegram_public_url.public_url()` (must be public HTTPS).
`to` is optional and only a request: the server decides the final redirect against the gateway's allowed paths.

## Wiring it to Telegram

- Menu button: `setChatMenuButton` with `{"type": "web_app", "text": "Open Huf", "web_app": {"url": <helper URL>}}`.
- Inline button: `InlineKeyboardButton(text="Open report", web_app=WebAppInfo(url=<helper URL>))`.

Use a `web_app` button, not a plain `url` button: only Mini Apps receive `initData`.

## Flow

1. User taps the button; Telegram opens `/tg_open` in its in-app browser with signed `initData`.
2. Page checks the environment, then POSTs JSON `{init_data, gateway, to}` (same origin, cookies included).
3. On `{ok: true, redirect}` the page calls `location.replace(redirect)` (only a path starting with a single `/` is accepted).

One tap, no password.

## Telegram Web limitation

Telegram Web (web.telegram.org: platforms `weba`, `webk`, `web`) runs Mini Apps inside an iframe where third-party
cookies are blocked, so the session cannot persist. The page detects this before posting and shows
"Telegram Web cannot keep a sign-in here. Open this in the Telegram app on your phone or desktop."

## Messages

| Message | Meaning |
| --- | --- |
| Open this link from the Telegram app. | No `initData` (opened in a normal browser). |
| Telegram Web cannot keep a sign-in here. ... | Iframe or Telegram Web platform. |
| Not authorized. Ask your administrator. | Any server rejection (HTTP 403) or network error. Deliberately no detail; a Retry button is shown. |

The page is served with no-cache headers, has no secrets, and never renders the gateway name server-side.
