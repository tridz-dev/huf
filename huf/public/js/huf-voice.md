# HUF Voice Embed Bundle

Minimal, framework-free JavaScript bundle for third-party websites to mint voice sessions for HUF Agents.

## Installation

Add this script tag to your HTML:

```html
<script src="https://<your-huf-site>/assets/huf/js/huf-voice.js"></script>
```

## Usage

```javascript
// Initialize with your HUF site, publishable key, and agent name
const voiceClient = HufVoice.init({
  baseUrl: 'https://your-huf-site.com',
  publishableKey: 'pk_1234567890abcdef',  // starts with pk_
  agent: 'my-agent-docname'
});

// Start a session (uses the Agent's own saved voice engine config —
// startSession() takes no config; a publishable key is public by design)
voiceClient.startSession()
  .then(session => {
    console.log('Voice session ready:', session);
    // session contains connection metadata (e.g., a signed URL or sidecar session ID)
    // Opening a live audio connection with this metadata is not yet implemented by this bundle
  })
  .catch(err => {
    console.error('Failed to start voice session:', err.message);
  });
```

## Response

The `session` object contains connection metadata required to establish a live voice connection. The format depends on which voice engine your Agent uses (e.g. a signed WebSocket URL for ElevenLabs, or a session id + sidecar path for the realtime engine). Implementing the actual audio connection is a separate step beyond this bundle's scope.

## Error Handling

The returned Promise rejects with an `Error` if:
- The publishable key is invalid or revoked
- The agent does not exist
- The network request fails
- Frappe returns an error response

The error message is extracted from the Frappe error response for user-friendly debugging.
