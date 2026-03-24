/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0d0d12',
        surface: '#1a1a26',
        'surface-dark': '#12121a',
        hover: '#242433',
        border: '#2a2a3a',
        primary: '#7c3aed',
        'primary-hover': '#6d28d9',
      },
    },
  },
  plugins: [],
}
