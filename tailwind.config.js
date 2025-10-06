/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './newsflow/templates/**/*.html',
    './newsflow/**/templates/**/*.html',
    './newsflow/static/js/**/*.js',
    './node_modules/flowbite/**/*.js'
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          '50': '#f0f7fe',
          '100': '#deedfb',
          '200': '#c4e1f9',
          '300': '#9bcdf5',
          '400': '#5aa9ec',
          '500': '#4994e8',
          '600': '#3479dc',
          '700': '#2b64ca',
          '800': '#2951a4',
          '900': '#264782',
          '950': '#1c2d4f',
        },
        // Set primary colors as the default blue replacements
        blue: {
          '50': '#f0f7fe',
          '100': '#deedfb',
          '200': '#c4e1f9',
          '300': '#9bcdf5',
          '400': '#5aa9ec',
          '500': '#4994e8',
          '600': '#3479dc',
          '700': '#2b64ca',
          '800': '#2951a4',
          '900': '#264782',
          '950': '#1c2d4f',
        },
        // Dark mode specific colors
        dark: {
          'bg': {
            'primary': '#0f172a',   // slate-900
            'secondary': '#1e293b', // slate-800
            'tertiary': '#334155',  // slate-700
          },
          'surface': {
            'primary': '#1e293b',   // slate-800
            'secondary': '#334155', // slate-700
            'tertiary': '#475569',  // slate-600
          },
          'text': {
            'primary': '#f8fafc',   // slate-50
            'secondary': '#e2e8f0', // slate-200
            'tertiary': '#cbd5e1',  // slate-300
          },
          'border': {
            'primary': '#334155',   // slate-700
            'secondary': '#475569', // slate-600
          }
        }
      },
      fontFamily: {
        'sans': ['Inter', 'ui-sans-serif', 'system-ui'],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'pulse-soft': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      boxShadow: {
        'soft': '0 2px 15px -3px rgba(73, 148, 232, 0.1), 0 4px 6px -2px rgba(73, 148, 232, 0.05)',
        'primary': '0 4px 14px 0 rgba(73, 148, 232, 0.2)',
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms')({
      strategy: 'class',
    }),
    require('@tailwindcss/typography'),
    require('flowbite/plugin')({
      charts: true,
    }),
  ],
  // Enable dark mode
  darkMode: 'class',
}
