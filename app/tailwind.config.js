/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        orbitron: ['Orbitron', 'sans-serif'],
      },
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        // Palette 14 base + Purple accent
        neon: {
          blue: "#7f5af0",    // Electric purple (primary)
          purple: "#7f5af0",  // Same
          green: "#2cb67d"    // Success green
        },
        glass: {
          light: "rgba(255, 255, 254, 0.8)",
          dark: "rgba(39, 35, 67, 0.6)",
        }
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(127, 90, 240, 0.1)' },
          '100%': { boxShadow: '0 0 20px rgba(127, 90, 240, 0.3), 0 0 10px rgba(127, 90, 240, 0.5)' },
        }
      }
    },
  },
  plugins: [],
}
