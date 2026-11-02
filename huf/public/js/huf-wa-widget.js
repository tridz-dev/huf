/* Huf "Chat on WhatsApp" floating button. No dependencies.
 * <script src=".../assets/huf/js/huf-wa-widget.js" data-number="15551234567" data-text="Hi" data-ref="site"
 *   data-label="Chat on WhatsApp" data-position="right" async></script> */
(function () {
  var s = document.currentScript;
  if (!s || document.getElementById('huf-wa-widget')) return;
  var number = (s.getAttribute('data-number') || '').replace(/\D/g, '');
  if (!number) return;
  var text = s.getAttribute('data-text') || '';
  var ref = s.getAttribute('data-ref') || '';
  if (ref) text = (text + ' [ref:' + ref + ']').trim();
  var url = 'https://wa.me/' + number + (text ? '?text=' + encodeURIComponent(text) : '');
  var label = s.getAttribute('data-label') || 'Chat on WhatsApp';
  var side = s.getAttribute('data-position') === 'left' ? 'left' : 'right';

  var a = document.createElement('a');
  a.id = 'huf-wa-widget';
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.setAttribute('aria-label', label);
  a.textContent = label;
  var css = {
    position: 'fixed', bottom: '20px', zIndex: '2147483000', padding: '12px 18px',
    borderRadius: '999px', background: '#25D366', color: '#fff', font: '600 15px/1 system-ui, sans-serif',
    textDecoration: 'none', boxShadow: '0 4px 14px rgba(0,0,0,.25)',
  };
  css[side] = '20px';
  for (var k in css) a.style[k] = css[k];
  document.body.appendChild(a);
})();
