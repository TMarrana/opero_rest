/** Lido pelo binário standalone em tools/tailwindcss.exe — sem npm. */
module.exports = {
  content: ["./templates/**/*.html", "./**/templates/**/*.html", "./static/js/app.js"],
  theme: {
    extend: {
      colors: {
        carvao: "rgb(var(--cor-carvao) / <alpha-value>)",
        aco: "rgb(var(--cor-aco) / <alpha-value>)",
        superficie: "rgb(var(--cor-superficie) / <alpha-value>)",
        chama: "rgb(var(--cor-chama) / <alpha-value>)",
        servico: "rgb(var(--cor-servico) / <alpha-value>)",
        ardosia: "rgb(var(--cor-ardosia) / <alpha-value>)",
      },
      fontFamily: {
        display: ["Archivo", "system-ui", "sans-serif"],
        corpo: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        dados: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      minHeight: { toque: "48px" },
      minWidth: { toque: "48px" },
    },
  },
  plugins: [],
};
