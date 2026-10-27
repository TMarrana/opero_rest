/** Lido pelo binário standalone em tools/tailwindcss.exe — sem npm.
    Tokens da secção 4 do plan.md. As cores base vivem em static/src/input.css;
    os tons claros e escuros são escalas fixas, para não se usar transparência
    sobre o creme (que dá tons diferentes conforme o fundo). */
const base = (nome) => `rgb(var(--cor-${nome}) / <alpha-value>)`;

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
        carvao: base("carvao"),
        creme: base("creme"),
        areia: base("areia"),
        linha: base("linha"),
        superficie: base("superficie"),
        ardosia: base("ardosia"),
        // Neutro quente, do creme à tinta.
        neutro: {
          50: "#FDFBF7",
          100: "#F7F2E8",
          200: "#EFE8DC",
          300: "#E2D8CA",
          400: "#C9BFB0",
          500: "#9C9387",
          600: "#6E675B",
          700: "#4E483F",
          800: "#36322B",
          900: "#221E18",
        },
        floresta: {
          DEFAULT: base("floresta"),
          50: "#EEF4F1",
          100: "#DCE7E2",
          200: "#B6CCC3",
          300: "#86A99B",
          400: "#4F7A6A",
          500: "#2C5547",
          600: "#1E4237",
          700: "#15302B",
          800: "#10251F",
          900: "#0B1A16",
        },
        // Ação principal da página e contadores.
        chama: { DEFAULT: base("chama"), 50: "#FDF1EC", 100: "#FADFD3", 600: "#A83C15" },
        // Ações irreversíveis e erros.
        perigo: { DEFAULT: base("perigo"), 50: "#FEF3F2", 100: "#FEE4E2", 200: "#FECDCA", 700: "#912018" },
        // Avisos: stock baixo, registos por resolver, linhas sem custo.
        alerta: { DEFAULT: base("alerta"), 50: "#FFF6ED", 100: "#FDEAD7", 200: "#F9DBAF", 700: "#93370D" },
        servico: { DEFAULT: base("servico"), 50: "#ECF6EF", 100: "#D5EBDC", 700: "#256B42" },
        ambar: { DEFAULT: base("ambar"), 50: "#FEF7EA", 100: "#FCEBCB", 700: "#8A5A10" },
      },
      fontFamily: {
        display: ["'Playfair Display'", "Georgia", "serif"],
        corpo: ["Inter", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        dados: ["Inter", "system-ui", "sans-serif"],
      },
      minHeight: { toque: "48px" },
      minWidth: { toque: "48px" },
      // Elevação em três níveis: cartão, cartão em foco, modal.
      boxShadow: {
        cartao: "0 1px 2px rgb(34 30 24 / 0.05), 0 1px 3px rgb(34 30 24 / 0.04)",
        elevado: "0 2px 4px rgb(34 30 24 / 0.04), 0 8px 20px -4px rgb(34 30 24 / 0.10)",
        flutuante: "0 24px 48px -12px rgb(21 48 43 / 0.28)",
        campo: "inset 0 1px 2px rgb(34 30 24 / 0.05)",
      },
    },
  },
  plugins: [],
};
