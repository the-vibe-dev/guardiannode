/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Brand kit: Inter for body/UI, Sora for headings (see assets/brand/README.md)
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        display: ["Sora", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          // Official palette: Deep Teal #0D3B4A primary, Forest Green #275E3D secondary
          50: "#f3f6f8",
          100: "#d7e4ea",
          500: "#275e3d",
          600: "#1c4a30",
          700: "#0d3b4a",
        },
        severity: {
          critical: "#b71c1c",
          high: "#ef6c00",
          medium: "#f9a825",
          low: "#1976d2",
          none: "#9e9e9e",
        },
      },
    },
  },
  plugins: [],
};
