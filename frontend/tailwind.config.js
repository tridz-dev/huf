/** @type {import('tailwindcss').Config} */
export default {
  // HUF design system is light-mode only (no .dark surface tokens are defined) —
  // disable the dark variant so stray `dark:` classes stay documented no-ops
  // instead of reacting to OS-level prefers-color-scheme.
  darkMode: false,
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // HUF Design System tokens
        paper:          'var(--paper)',
        'paper-deep':   'var(--paper-deep)',
        panel:          'var(--panel)',
        ink:            'var(--ink)',
        'ink-soft':     'var(--ink-soft)',
        steel:          'var(--steel)',
        'steel-soft':   'var(--steel-soft)',
        line:           'var(--line)',
        'line-dark':    'var(--line-dark)',
        signal:         'var(--signal)',
        'signal-ink':   'var(--signal-ink)',
        good:           'var(--good)',
        'good-tint':    'var(--good-tint)',
        'destructive-tint': 'var(--destructive-tint)',
        warning:        'var(--warning)',
        'warning-tint': 'var(--warning-tint)',
        'chat-row-hover':    'var(--chat-row-hover)',
        'chat-row-selected': 'var(--chat-row-selected)',
        'chat-bubble':       'var(--chat-bubble)',

        // shadcn compatibility
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: {
          DEFAULT:    'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        popover: {
          DEFAULT:    'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        primary: {
          DEFAULT:    'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT:    'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        muted: {
          DEFAULT:    'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT:    'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        destructive: {
          DEFAULT:    'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        border: 'var(--border)',
        input:  'var(--input)',
        ring:   'var(--ring)',
        sidebar: {
          DEFAULT:              'var(--sidebar-background)',
          foreground:           'var(--sidebar-foreground)',
          primary:              'var(--sidebar-primary)',
          'primary-foreground': 'var(--sidebar-primary-foreground)',
          accent:               'var(--sidebar-accent)',
          'accent-foreground':  'var(--sidebar-accent-foreground)',
          border:               'var(--sidebar-border)',
          ring:                 'var(--sidebar-ring)',
        },
      },
      spacing: {
        'space-1': 'var(--space-1)',
        'space-2': 'var(--space-2)',
        'space-3': 'var(--space-3)',
        'space-4': 'var(--space-4)',
        'space-5': 'var(--space-5)',
        'space-6': 'var(--space-6)',
        'space-7': 'var(--space-7)',
        // NOTE: Tailwind's px-{key}/py-{key} utilities both look up the
        // *same* `spacing` theme namespace, keyed only by what follows the
        // axis prefix — so `px-control` and `py-control` would collide on
        // one shared key/value if both used the literal key "control".
        // Horizontal and vertical control padding differ (16px vs 8px), so
        // they need distinct key names: 'control' (→ px-control) vs
        // 'control-y' (→ py-control-y). Do not name these back to
        // 'control-px'/'control-py' — that produces classes px-control-px /
        // py-control-py, which don't match what button.tsx actually uses
        // (px-control / py-control-y), silently generating no CSS at all.
        'control':       'var(--control-px)',
        'control-sm':    'var(--control-px-sm)',
        'control-lg':    'var(--control-px-lg)',
        'control-y':     'var(--control-py)',
        'chat-turn':     'var(--chat-turn-gap)',
        'chat-rail':     'var(--chat-rail-w)',
      },
      height: {
        'control-sm': 'var(--control-h-sm)',
        'control-md': 'var(--control-h-md)',
        'control-lg': 'var(--control-h-lg)',
        'chat-row':    'var(--chat-row-h)',
        'chat-header': 'var(--chat-header-h)',
        'chat-footer': 'var(--chat-footer-h)',
      },
      width: {
        'control-sm': 'var(--control-h-sm)',
        'control-md': 'var(--control-h-md)',
        'control-lg': 'var(--control-h-lg)',
        'chat-rail': 'var(--chat-rail-w)',
      },
      maxWidth: {
        'chat-measure': 'var(--chat-measure)',
      },
      borderRadius: {
        DEFAULT: 'var(--r)',
        lg:      'var(--r-lg, var(--r))',
        md:      'var(--r-md, var(--r))',
        sm:      'var(--r-sm, var(--r))',
        full:    'var(--r-full, var(--r))',
        xl:      'var(--r-xl, var(--r))',
        '2xl':   'var(--r-xl, var(--r))',
        '3xl':   'var(--r-xl, var(--r))',
        none:    '0',
        'chat-row': 'var(--chat-row-r)',
      },
      boxShadow: {
        DEFAULT: 'var(--shadow-flat, none)',
        sm:      'var(--shadow-flat, none)',
        md:      'var(--shadow-raised, none)',
        lg:      'var(--shadow-overlay, none)',
        xl:      'var(--shadow-overlay, none)',
        '2xl':   'var(--shadow-overlay, none)',
        inner:   'none',
        none:    'none',
      },
      fontFamily: {
        display: 'var(--display)',
        body:    'var(--body)',
        mono:    'var(--mono)',
        sans:    'var(--body)',
      },
      fontSize: {
        // Admin/backend-UI type scale — additive only, does not touch
        // Tailwind's default text-sm/base/lg/xl scale used throughout the app.
        display: [
          'var(--text-display-size)',
          { letterSpacing: 'var(--text-display-tracking)', fontWeight: 'var(--text-display-weight)' },
        ],
        title: [
          'var(--text-title-size)',
          { letterSpacing: 'var(--text-title-tracking)', fontWeight: 'var(--text-title-weight)' },
        ],
        // 18px section/card header — added to close the 15px→20px gap that
        // 6 callsites were independently working around.
        subtitle: [
          'var(--text-subtitle-size)',
          { fontWeight: 'var(--text-subtitle-weight)' },
        ],
        // 12px dense form/table text — closes the 11px→13px gap that 15+
        // callsites were working around.
        micro: [
          'var(--text-micro-size)',
          { fontWeight: 'var(--text-micro-weight)' },
        ],
        // Named 'body-text' (not 'body') to avoid ambiguity with the
        // `body` fontFamily key above (font-body vs text-body-text).
        'body-text': [
          'var(--text-body-size)',
          { fontWeight: 'var(--text-body-weight)' },
        ],
        'ui-text': [
          'var(--text-ui-size)',
          { fontWeight: 'var(--text-ui-weight)' },
        ],
        meta: ['var(--text-meta-size)', {}],
        eyebrow: [
          'var(--text-eyebrow-size)',
          { letterSpacing: 'var(--text-eyebrow-tracking)' },
        ],
      },
      keyframes: {
        blink: { '50%': { opacity: '.2' } },
        drop: {
          from: { opacity: '0', transform: 'translateY(-6px)' },
          to:   { opacity: '1', transform: 'none' },
        },
        'accordion-down': {
          from: { height: '0' },
          to:   { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to:   { height: '0' },
        },
      },
      animation: {
        blink:            'blink 1.6s steps(2) infinite',
        drop:             'drop 0.35s ease-out',
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up':   'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};
