/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/admin_panel/**/*.html",
    "./src/admin_panel/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#06b6d4', dark: '#0891b2', light: '#67e8f9' },
      },
    },
  },
  plugins: [],
}
