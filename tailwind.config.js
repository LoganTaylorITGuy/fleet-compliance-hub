/** Tailwind is compiled ahead of time so the demo works offline.
 *  Rebuild after changing templates:  npm run build:css  */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js", "./app/**/*.py"],
  theme: { extend: {} },
  plugins: [],
};
