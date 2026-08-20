/** @type {import('tailwindcss').Config} */
// Design system do Projeto Crianca Feliz.
// Build: (dentro de tailwindcss/)  npm install  &&  npm run build
// Saida: ../static/css/pcf.css  (commitada; PythonAnywhere so faz git pull)
module.exports = {
  // Preflight OFF: o Bootstrap ainda é carregado nas telas não-migradas durante a
  // transição; o reset do Tailwind brigaria com o Reboot do Bootstrap. Base additiva
  // fica no @layer base do input.css. Removido no ciclo final de limpeza.
  corePlugins: { preflight: false },
  // O design system .pcf-* é uma biblioteca estável: nunca purgar, mesmo que
  // uma classe ainda não apareça em nenhum template.
  safelist: [{ pattern: /^pcf-/ }],
  content: [
    "../templates/**/*.html",
    "../atendido/**/*.html",
    "../voluntario/**/*.html",
    "../semanario/**/*.html",
    "../sabado/**/*.html",
    "../supply/**/*.html",
    "../adm/**/*.html",
    "../forms_pcf/**/*.html",
    "../ronda/**/*.html",
    "../gerenciamento/**/*.html",
    // Apps novos. Faltando aqui, classe usada SO neles e purgada em
    // silencio e a tela quebra sem erro nenhum.
    "../parceiros/**/*.html",
    "../editais/**/*.html",
    "../revista/**/*.html",
    "../projetos/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Marca PCF (laranja quente) + tinta + acentos de categoria.
        brand: {
          50: "#fff6f0",
          100: "#fff0e6",
          200: "#fbe3d3",
          300: "#ffb47a",
          400: "#ff9040",
          500: "#ff8a3d",
          600: "#f26b21",
          700: "#e04e0c",
          800: "#c93f05",
          900: "#8a3412",
        },
        ink: {
          DEFAULT: "#1c130e",
          soft: "#5a4a41",
          muted: "#8a7566",
          faint: "#a08d80",
        },
        cream: {
          DEFAULT: "#fffaf6",
          deep: "#fff6f0",
        },
        night: {
          DEFAULT: "#1a100c",
          600: "#241610",
          500: "#2a1710",
          card: "#1f1410",
          cardEnd: "#2b1a12",
        },
        cat: {
          green: "#2e8b57",
          greenTint: "#eaf7ef",
          blue: "#3b62b3",
          blueTint: "#eaf0fb",
          gold: "#b8860b",
          goldTint: "#fdf3dd",
        },
      },
      fontFamily: {
        sans: ["Archivo", "system-ui", "sans-serif"],
        display: ["Archivo", "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        island: "42px",
      },
      boxShadow: {
        warm: "0 30px 60px -44px rgba(120,50,10,.6)",
        "warm-sm": "0 20px 40px -24px rgba(120,50,10,.5)",
        "warm-lg": "0 40px 80px -30px rgba(70,20,0,.6)",
        glow: "0 20px 36px -18px rgba(234,84,17,.9)",
      },
      keyframes: {
        floaty: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-14px)" } },
        pulseGlow: { "0%,100%": { opacity: ".55" }, "50%": { opacity: "1" } },
        riseIn: { from: { opacity: "0", transform: "translateY(18px)" }, to: { opacity: "1", transform: "none" } },
        orbit: { from: { transform: "rotate(0deg)" }, to: { transform: "rotate(360deg)" } },
      },
      animation: {
        floaty: "floaty 6s ease-in-out infinite",
        pulseGlow: "pulseGlow 7s ease-in-out infinite",
        riseIn: "riseIn .7s ease both",
        orbit: "orbit 22s linear infinite",
      },
    },
  },
  plugins: [],
}
