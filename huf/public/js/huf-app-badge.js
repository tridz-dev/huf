/**
 * huf-app-badge.js - "Back to HUF" pill for provider apps.
 * Usage: <script src="/assets/huf/js/huf-app-badge.js" defer></script>
 * data-* overrides:
 *   data-position bottom-right (default) | bottom-left | top-right | top-left
 *   data-label pill text (default "← HUF")
 *   data-href link target (default "/huf/apps")
 *   data-new-tab "true" → target="_blank" rel="noopener"
 *   data-theme auto (default; prefers-color-scheme) | light | dark
 * Never throws or duplicates.
 */
(function () {
	// document.currentScript is null in callbacks.
	var script = document.currentScript;
	function init() {
		try {
			if (!script || document.getElementById('huf-app-badge')) return;
			var d = script.dataset || {},
				m = window.matchMedia,
				pos = /^(bottom|top)-(right|left)$/.test(d.position) ? d.position : 'bottom-right',
				theme = /^(light|dark)$/.test(d.theme) ? d.theme : 'auto',
				dark = theme === 'dark' || (theme === 'auto' && m && m('(prefers-color-scheme: dark)').matches),
				c = dark ? ['#e5e7eb', 'rgba(31,41,55,.9)', 'rgba(255,255,255,.16)'] : ['#1f2937', 'rgba(255,255,255,.9)', 'rgba(0,0,0,.12)'],
				off = ':16px;',
				a = document.createElement('a'),
				s = a.style;
			a.id = 'huf-app-badge';
			a.href = d.href || '/huf/apps';
			a.textContent = d.label || '← HUF';
			if (d.newTab === 'true') { a.target = '_blank'; a.rel = 'noopener'; }
			s.cssText = 'position:fixed;z-index:9999;padding:8px 12px;border-radius:999px;text-decoration:none;opacity:.45;font:12px system-ui,sans-serif;'
				+ (pos[0] === 't' ? 'top' : 'bottom') + off + (pos.indexOf('left') > 0 ? 'left' : 'right') + off
				+ 'color:' + c[0] + ';background:' + c[1] + ';border:1px solid ' + c[2];
			a.onmouseenter = function () { s.opacity = 1; s.boxShadow = '0 2px 8px rgba(0,0,0,.2)'; };
			a.onmouseleave = function () { s.opacity = '.45'; s.boxShadow = 'none'; };
			document.body.appendChild(a);
		} catch (e) {}
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
	else init();
})();
