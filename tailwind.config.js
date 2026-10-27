/** Lido pelo binário standalone em tools/tailwindcss.exe — sem npm.
    Tokens da secção 4 do plan.md: os valores vivem em static/src/input.css. */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./static/js/app.js",
    "./core/templatetags/*.py",
    "./*/forms.py",
    "./*/*views.py",
  ],
  theme: {
    extend: {
      colors: {
        carvao: "rgb(var(--cor-carvao) / <alpha-value>)",
        floresta: "rgb(var(--cor-floresta) / <alpha-value>)",
        creme: "rgb(var(--cor-creme) / <alpha-value>)",
        areia: "rgb(var(--cor-areia) / <alpha-value>)",
        linha: "rgb(var(--cor-linha) / <alpha-value>)",
        superficie: "rgb(var(--cor-superficie) / <alpha-value>)",
        chama: "rgb(var(--cor-chama) / <alpha-value>)",
        servico: "rgb(var(--cor-servico) / <alpha-value>)",
        ambar: "rgb(var(--cor-ambar) / <alpha-value>)",
        ardosia: "rgb(var(--cor-ardosia) / <alpha-value>)",
      },
      fontFamily: {
        display: ["'Playfair Display'", "Georgia", "serif"],
        corpo: ["Inter", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        dados: ["Inter", "system-ui", "sans-serif"],
      },
      minHeight: { toque: "48px" },
      minWidth: { toque: "48px" },
      borderRadius: { "4xl": "1.75rem" },
      boxShadow: {
        cartao: "0 1px 2px rgb(34 30 24 / 0.04)",
        flutuante: "0 16px 40px -12px rgb(21 48 43 / 0.28)",
      },
    },
  },
  plugins: [],
};
