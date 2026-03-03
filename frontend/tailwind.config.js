/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bharat: {
          saffron: "#FF9933",
          white: "#FFFFFF",
          green: "#128807",
          navy: "#000080",
        },
      },
    },
  },
  plugins: [],
}
