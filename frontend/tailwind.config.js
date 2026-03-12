/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          black: '#000000',
          gold: '#B49B7F',
          'gold-light': '#C9B59A',
          'gold-dark': '#9A8369',
        },
      },
    },
  },
  plugins: [],
}
