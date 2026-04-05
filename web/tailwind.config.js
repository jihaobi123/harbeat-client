/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#FF6A2A', dark: '#E8500B' },
        surface: { DEFAULT: '#F5F5F0', light: '#F3EBDD', lighter: '#FFFFFF' },
        accent: '#9C57E7',
      },
    },
  },
  plugins: [],
}
