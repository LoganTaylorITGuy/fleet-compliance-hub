/** Tailwind is compiled ahead of time so the demo works offline.
 *  Rebuild after changing templates:  npm run build:css
 *
 *  Colors are design tokens backed by CSS variables (app/static/css/input.css),
 *  so every utility below switches between light and dark automatically.
 *  Use these names in templates, never raw palette colors like slate-600.
 */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js", "./app/**/*.py"],
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"),
        ink: token("ink"),
        muted: token("muted"),
        subtle: token("subtle"),
        line: { DEFAULT: token("line"), strong: token("line-strong") },
        tint: token("tint"),
        field: token("field"),
        accent: { DEFAULT: token("accent"), strong: token("accent-strong") },
        "on-accent": token("on-accent"),
        link: { DEFAULT: token("link"), strong: token("link-strong") },
        danger: { soft: token("danger-soft"), ink: token("danger-ink"), line: token("danger-line"), solid: token("danger-solid") },
        warn: { soft: token("warn-soft"), ink: token("warn-ink"), line: token("warn-line") },
        ok: { soft: token("ok-soft"), ink: token("ok-ink"), line: token("ok-line"), solid: token("ok-solid") },
        info: { soft: token("info-soft"), ink: token("info-ink"), line: token("info-line") },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", '"SF Pro Text"', '"Segoe UI"', "Inter", "Roboto", "Helvetica", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
};
