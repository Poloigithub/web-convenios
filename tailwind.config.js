/** Configuración de Tailwind (build con el CLI standalone en el workflow).
    Los colores ctp-* son variables CSS: Catppuccin Latte de día y Mocha
    de noche, definidas en web/tailwind.css. */
module.exports = {
  content: ["./web/**/*.{html,js}"],
  theme: {
    extend: {
      colors: {
        ctp: {
          base: "var(--ctp-base)",
          mantle: "var(--ctp-mantle)",
          crust: "var(--ctp-crust)",
          surface0: "var(--ctp-surface0)",
          surface1: "var(--ctp-surface1)",
          surface2: "var(--ctp-surface2)",
          overlay0: "var(--ctp-overlay0)",
          overlay1: "var(--ctp-overlay1)",
          subtext0: "var(--ctp-subtext0)",
          subtext1: "var(--ctp-subtext1)",
          text: "var(--ctp-text)",
          red: "var(--ctp-red)",
          maroon: "var(--ctp-maroon)",
          peach: "var(--ctp-peach)",
          yellow: "var(--ctp-yellow)",
          green: "var(--ctp-green)",
          teal: "var(--ctp-teal)",
          blue: "var(--ctp-blue)",
          lavender: "var(--ctp-lavender)",
          mauve: "var(--ctp-mauve)",
        },
      },
    },
  },
};
