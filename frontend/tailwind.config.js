/** @type {import('tailwindcss').Config} */
export default {
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
      borderRadius: {
        DEFAULT: '2px',
        lg:      '2px',
        md:      '2px',
        sm:      '2px',
        none:    '0',
      },
      fontFamily: {
        display: ['Big Shoulders Display', 'sans-serif'],
        body:    ['Archivo', 'sans-serif'],
        mono:    ['Martian Mono', 'monospace'],
        sans:    ['Archivo', 'sans-serif'],
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
