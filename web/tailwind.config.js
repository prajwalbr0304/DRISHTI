/** DRISHTI — "Calm Authority" Tailwind theme.
 *  Colour tokens are CSS variables (see src/index.css) so a single class set
 *  serves both Ops (dark, default) and Desk (light) themes. Type scale, radii
 *  and the 8-pt grid follow doc 01 §2. Tremor tokens are mapped onto the same
 *  system so dashboard components inherit the design language.
 */

import tailwindcssAnimate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "./node_modules/@tremor/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // --- Calm Authority core tokens (theme-swapped CSS vars) ---
        bg: "var(--bg)",
        surface: {
          DEFAULT: "var(--surface)",
          2: "var(--surface-2)",
        },
        hairline: "var(--border)",
        content: {
          DEFAULT: "var(--text)",
          dim: "var(--text-dim)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          fg: "var(--primary-fg)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          fg: "var(--accent-fg)",
        },
        // --- Semantic severity (never decorative; always paired w/ icon+label) ---
        severity: {
          critical: "var(--sev-critical)",
          high: "var(--sev-high)",
          medium: "var(--sev-medium)",
          low: "var(--sev-low)",
        },
        // --- The one fixed 12-hue category palette (assigned once) ---
        cat: {
          1: "var(--cat-1)",
          2: "var(--cat-2)",
          3: "var(--cat-3)",
          4: "var(--cat-4)",
          5: "var(--cat-5)",
          6: "var(--cat-6)",
          7: "var(--cat-7)",
          8: "var(--cat-8)",
          9: "var(--cat-9)",
          10: "var(--cat-10)",
          11: "var(--cat-11)",
          12: "var(--cat-12)",
        },
        // --- Tremor token bridge (dashboard components) ---
        tremor: {
          brand: {
            faint: "var(--surface-2)",
            muted: "var(--surface-2)",
            subtle: "var(--primary)",
            DEFAULT: "var(--primary)",
            emphasis: "var(--primary)",
            inverted: "var(--surface)",
          },
          background: {
            muted: "var(--surface-2)",
            subtle: "var(--surface-2)",
            DEFAULT: "var(--surface)",
            emphasis: "var(--text-dim)",
          },
          border: { DEFAULT: "var(--border)" },
          ring: { DEFAULT: "var(--border)" },
          content: {
            subtle: "var(--text-dim)",
            DEFAULT: "var(--text-dim)",
            emphasis: "var(--text)",
            strong: "var(--text)",
            inverted: "var(--bg)",
          },
        },
        "dark-tremor": {
          brand: {
            faint: "var(--surface-2)",
            muted: "var(--surface-2)",
            subtle: "var(--primary)",
            DEFAULT: "var(--primary)",
            emphasis: "var(--primary)",
            inverted: "var(--surface)",
          },
          background: {
            muted: "var(--surface-2)",
            subtle: "var(--surface-2)",
            DEFAULT: "var(--surface)",
            emphasis: "var(--text-dim)",
          },
          border: { DEFAULT: "var(--border)" },
          ring: { DEFAULT: "var(--border)" },
          content: {
            subtle: "var(--text-dim)",
            DEFAULT: "var(--text-dim)",
            emphasis: "var(--text)",
            strong: "var(--text)",
            inverted: "var(--bg)",
          },
        },
      },
      fontFamily: {
        // AWS console typography: Amazon Ember is the console face and resolves
        // locally on machines that have it; Open Sans is Cloudscape's published
        // default and is webfont-loaded, so the metrics match everywhere else.
        // Local system Kannada faces (Nirmala UI/Tunga/Kedage) are fallbacks so
        // Kannada renders even when the webfont CDN is unreachable (doc 01 §9).
        sans: [
          "Amazon Ember",
          "Open Sans",
          "Noto Sans Kannada",
          "Nirmala UI",
          "Tunga",
          "Kedage",
          "Helvetica Neue",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        kannada: ["Noto Sans Kannada", "Nirmala UI", "Tunga", "Kedage", "Open Sans", "sans-serif"],
        mono: ["Monaco", "Menlo", "Consolas", "Courier Prime", "Courier", "Courier New", "monospace"],
      },
      fontSize: {
        /* --- Cloudscape / AWS console type scale (the canonical set) ---------
           Heading styles are Bold (700); body styles Normal (400).
           https://cloudscape.design/foundation/visual-foundation/typography/ */
        "heading-xl": ["24px", { lineHeight: "30px" }], // page title (h1)
        "heading-l": ["20px", { lineHeight: "24px" }], // container / widget title (h2)
        "heading-m": ["18px", { lineHeight: "22px" }], // card section header (h3)
        "heading-s": ["16px", { lineHeight: "20px" }], // paragraph title (h4)
        "heading-xs": ["14px", { lineHeight: "18px" }], // sub-paragraph (h5)
        "body-m": ["14px", { lineHeight: "20px" }], // body + paragraph text
        "body-s": ["12px", { lineHeight: "16px" }], // description / constraint text
        "display-l": ["42px", { lineHeight: "48px" }], // dashboard number highlights

        /* --- Legacy px-named scale (doc 01 §2.2) kept so existing screens
           compile. NOTE: 11/15/17/18/32 were referenced across the app but were
           never declared here, so `text-11` & friends emitted NO css and those
           call sites silently inherited their parent size. They are declared now
           and snapped onto the Cloudscape scale — including its "never below
           12px" rule, which is why `11` resolves to 12px. */
        11: ["12px", { lineHeight: "16px" }], // → body-s (12px floor)
        12: ["12px", { lineHeight: "16px" }],
        13: ["13px", { lineHeight: "18px" }],
        14: ["14px", { lineHeight: "20px" }],
        15: ["14px", { lineHeight: "20px" }], // → body-m
        16: ["16px", { lineHeight: "24px" }],
        17: ["16px", { lineHeight: "20px" }], // → heading-s
        18: ["18px", { lineHeight: "22px" }], // → heading-m
        20: ["20px", { lineHeight: "28px" }],
        28: ["28px", { lineHeight: "34px" }],
        32: ["32px", { lineHeight: "40px" }], // landing hero only
        36: ["36px", { lineHeight: "42px" }],
        // Tremor scale bridge
        "tremor-label": ["12px", { lineHeight: "16px" }],
        "tremor-default": ["14px", { lineHeight: "20px" }],
        "tremor-title": ["20px", { lineHeight: "24px" }],
        "tremor-metric": ["28px", { lineHeight: "34px" }],
      },
      borderRadius: {
        // Cloudscape visual-refresh radii: 16px containers, 8px inputs/items,
        // 4px badges, pill buttons.
        card: "16px",
        control: "8px",
        item: "8px",
        badge: "4px",
        "tremor-small": "8px",
        "tremor-default": "16px",
        "tremor-full": "9999px",
      },
      spacing: {
        // 8-pt grid helpers (Tailwind's 4px base already covers 2/4/6 = 8/16/24)
        rail: "15rem", // 240px expanded side nav (AWS uses ~280px; 240 fits the
        //                 longest destination label without truncation)
        "rail-collapsed": "3.5rem", // 56px icon rail
        peek: "26rem", // 416px peek rail
        topbar: "3.25rem", // 52px
        breadcrumb: "2.5rem", // 40px
        subnav: "13rem",
      },
      boxShadow: {
        // Cloudscape container elevation: flat and wide, not a tight drop shadow.
        card: "0 1px 8px 2px rgb(0 0 0 / 0.20)",
        rail: "0 0 0 1px var(--border)",
        peek: "-8px 0 24px -12px rgb(0 0 0 / 0.45)",
        pop: "0 8px 28px -8px rgb(0 0 0 / 0.45), 0 0 0 1px var(--border)",
        "tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        "tremor-card": "0 1px 8px 2px rgb(0 0 0 / 0.20)",
        "tremor-dropdown": "0 8px 28px -8px rgb(0 0 0 / 0.45)",
      },
      keyframes: {
        // The ONLY looping animation in the product: the red-zone alert pulse.
        "redzone-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgb(239 68 68 / 0.55)" },
          "70%": { boxShadow: "0 0 0 12px rgb(239 68 68 / 0)" },
          "100%": { boxShadow: "0 0 0 0 rgb(239 68 68 / 0)" },
        },
        /* --- Face-scan feedback -------------------------------------------
           These loop, which the motion budget above otherwise forbids. They are
           PROGRESS INDICATORS, scoped to the face-scan viewport and mounted only
           while a scan is actually in flight — the same exception the existing
           `animate-spin` spinner relies on. Nothing here loops on an idle screen,
           and every one of them is suppressed under prefers-reduced-motion. */
        "face-sweep": {
          "0%": { transform: "translateY(-8%)", opacity: "0" },
          "12%": { opacity: "1" },
          "88%": { opacity: "1" },
          "100%": { transform: "translateY(108%)", opacity: "0" },
        },
        "face-scanline-glow": {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "0.9" },
        },
        // Corner brackets settling onto the detected face box.
        "face-lock": {
          from: { transform: "scale(1.14)", opacity: "0" },
          to: { transform: "scale(1)", opacity: "1" },
        },
        // Staggered dossier reveal (one-shot, 220ms).
        "face-reveal": {
          from: { transform: "translateY(6px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        "face-tick": {
          from: { transform: "translateX(-4px)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in-right": {
          from: { transform: "translateX(12px)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "redzone-pulse": "redzone-pulse 1.8s cubic-bezier(0.4,0,0.6,1) infinite",
        // Face-scan progress feedback (see the keyframes note above).
        "face-sweep": "face-sweep 1.5s cubic-bezier(0.45,0,0.55,1) infinite",
        "face-scanline-glow": "face-scanline-glow 1.5s ease-in-out infinite",
        "face-lock": "face-lock 260ms cubic-bezier(0.16,1,0.3,1) both",
        "face-reveal": "face-reveal 220ms ease-out both",
        "face-tick": "face-tick 180ms ease-out both",
        "fade-in": "fade-in 160ms ease-out",
        "slide-in-right": "slide-in-right 180ms ease-out",
        "accordion-down": "accordion-down 180ms ease-out",
        "accordion-up": "accordion-up 180ms ease-out",
      },
      transitionDuration: {
        // doc 01 §2.3 — 150–200ms informative motion
        150: "150ms",
        180: "180ms",
        200: "200ms",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
