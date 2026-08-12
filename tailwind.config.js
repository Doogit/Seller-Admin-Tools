/** Tailwind v3 config for the standalone CLI (no Node, no PostCSS plugins).
 *  Content = the FastHTML view code where class="" strings live, so the
 *  built web/static/tailwind.css is tree-shaken to only classes actually used.
 *  Keep this in sync with `make css`.
 */
module.exports = {
  content: ["./web/**/*.py"],
  theme: {
    extend: {},
  },
  plugins: [],
};
