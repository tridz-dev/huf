/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
  	extend: {
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			background: 'oklch(var(--background))',
  			foreground: 'oklch(var(--foreground))',
  			card: {
  				DEFAULT: 'oklch(var(--card))',
  				foreground: 'oklch(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'oklch(var(--popover))',
  				foreground: 'oklch(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'oklch(var(--primary))',
  				foreground: 'oklch(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'oklch(var(--secondary))',
  				foreground: 'oklch(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'oklch(var(--muted))',
  				foreground: 'oklch(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'oklch(var(--accent))',
  				foreground: 'oklch(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'oklch(var(--destructive))',
  				foreground: 'oklch(var(--destructive-foreground))'
  			},
  			border: 'oklch(var(--border))',
  			input: 'oklch(var(--input))',
  			ring: 'oklch(var(--ring))',
  			chart: {
  				'1': 'oklch(var(--chart-1))',
  				'2': 'oklch(var(--chart-2))',
  				'3': 'oklch(var(--chart-3))',
  				'4': 'oklch(var(--chart-4))',
  				'5': 'oklch(var(--chart-5))'
  			},
  			sidebar: {
  				DEFAULT: 'hsl(var(--sidebar-background))',
  				foreground: 'hsl(var(--sidebar-foreground))',
  				primary: 'hsl(var(--sidebar-primary))',
  				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
  				accent: 'hsl(var(--sidebar-accent))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
  				border: 'hsl(var(--sidebar-border))',
  				ring: 'hsl(var(--sidebar-ring))'
  			}
  		},
  		keyframes: {
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		animation: {
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		}
  	}
  },
  plugins: [require('tailwindcss-animate')],
};
