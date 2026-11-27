/** `<huf-flow-builder>`: the custom element host pages use. A wrapper around `mountFlowBuilder`. */
import { mountFlowBuilder, type MountHandle, type MountOptions } from './mount';

function parseTokens(raw: string | null): Record<string, string> | undefined {
  if (!raw) return undefined;
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, string>) : undefined;
  } catch {
    return undefined;
  }
}

class HufFlowBuilder extends HTMLElement {
  static observedAttributes = ['flow', 'app', 'src-origin', 'mode', 'theme', 'run'];
  private handle: MountHandle | null = null;

  connectedCallback() {
    this.style.display ||= 'block';
    this.style.height ||= '100%';
    this.sync();
  }

  disconnectedCallback() {
    this.handle?.destroy();
    this.handle = null;
  }

  attributeChangedCallback(_name: string, before: string | null, after: string | null) {
    if (before !== after && this.isConnected) this.sync();
  }

  private sync() {
    const flow = this.getAttribute('flow');
    const app = this.getAttribute('app');
    if (!flow || !app) {
      this.disconnectedCallback();
      return;
    }
    const mode = this.getAttribute('mode');
    const options: MountOptions = {
      flow,
      app,
      srcOrigin: this.getAttribute('src-origin') || undefined,
      mode: mode === 'light' || mode === 'dark' ? mode : undefined,
      tokens: parseTokens(this.getAttribute('theme')),
      run: this.getAttribute('run') || undefined,
    };
    if (this.handle) this.handle.update(options);
    else {
      this.handle = mountFlowBuilder(this, options, (event, detail) => {
        this.dispatchEvent(new CustomEvent(event, { detail }));
      });
    }
  }
}

if (!customElements.get('huf-flow-builder')) customElements.define('huf-flow-builder', HufFlowBuilder);
