/** Tailwind v3 config for the standalone CLI (no Node, no PostCSS plugins).
 *  Content = the FastHTML view code where class="" strings live, so the
 *  built web/static/tailwind.css is tree-shaken to only classes actually used.
 *  Keep this in sync with `make css`.
 *
 *  The design tokens below are the single source of truth for the web UI; the
 *  same brand accent is mirrored in core/styles.py (ACCENT_RGB) so the on-screen
 *  charts and the .pptx charts share one palette. Status colors are the
 *  Okabe-Ito colorblind-safe set (surfaced as chips/stripes with text labels,
 *  never color alone). No class name is ever built by interpolation, so every
 *  utility here can be statically tree-shaken.
 */
module.exports = {
  content: ["./web/**/*.py"],
  theme: {
    extend: {
      colors: {
        bg: "#F6F7F9",       // app background (cool-biased neutral)
        surface: "#FFFFFF",  // cards, tables
        border: "#E1E5EA",   // hairlines, dividers
        ink: "#171C24",      // primary text, data values
        muted: "#59616E",    // labels, captions, secondary text
        brand: {
          DEFAULT: "#0072B2", // action, link, active nav, chart bars
          dark: "#005B8F",    // hover
          tint: "#E7F1F8",    // subtle brand wash
        },
        // Okabe-Ito status set. `.ink` variants meet WCAG AA on the tint bg.
        high: { DEFAULT: "#D55E00", tint: "#FBEAE0", ink: "#8A3D00" },     // at-risk, errors
        medium: { DEFAULT: "#E69F00", tint: "#FBF1DC", ink: "#7A5600" },   // warnings, derived
        low: { DEFAULT: "#0072B2", tint: "#E7F1F8", ink: "#04568A" },      // neutral status/info
        positive: { DEFAULT: "#009E73", tint: "#E0F1EB", ink: "#076C50" }, // gains, confirmed
      },
    },
  },
  plugins: [],
};
