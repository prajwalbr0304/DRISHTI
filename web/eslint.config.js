// DRISHTI web — ESLint flat config (Prompt 22 A.3: a real, locked, working lint
// gate; lint is NOT removed from the pipeline just because it was unconfigured).
//
// Locked versions (see package.json devDependencies): eslint 9.39.5,
// @eslint/js 9.39.5, typescript-eslint 8.65.0, eslint-plugin-react-hooks 5.2.0,
// eslint-plugin-react-refresh 0.4.26, globals 15.15.0.
//
// Layout: (1) every TS/TSX file gets the typescript-eslint *recommended*
// (non type-checked) rules — fast, no tsconfig project; full type checking is
// the separate `npm run typecheck` (tsc --noEmit) gate. (2) src/*.tsx also gets
// the React-Hooks correctness rules as ERRORS (real bugs). (3) plain JS build
// scripts + root config files get the Node global set + base rules.

import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // Never lint build output, deps, coverage, generated typings.
    ignores: ["dist/**", "node_modules/**", "coverage/**", "**/*.d.ts"],
  },

  // --- (1) Every TypeScript file: TS parser + recommended rules -------------
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      // Browser app + Node config files (vite/vitest) share this parser block;
      // exposing both global sets avoids no-undef false positives either way.
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // Pragmatic settings for a large, working synthetic-demo codebase:
      // unused vars are warnings (underscore-prefixed are intentional), and
      // `any` is allowed (the API layer uses it deliberately at boundaries).
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "off",
    },
  },

  // --- (2) Application source (React) adds Hooks correctness rules ----------
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },

  // --- (3) Node build scripts + root JS config files ------------------------
  {
    files: ["**/*.{js,mjs,cjs}"],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.node },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },

  // --- (4) AudioWorklet processors (public/audio/*.js) ----------------------
  // These execute in the AudioWorklet global scope — not Node, not the main
  // window — so block (3)'s Node globals leave the worklet API undeclared and
  // `no-undef` fires on AudioWorkletProcessor / registerProcessor. Declared
  // explicitly rather than via a globals preset so this does not depend on the
  // `globals` package shipping an audioworklet set.
  {
    files: ["public/audio/**/*.js"],
    languageOptions: {
      globals: {
        AudioWorkletProcessor: "readonly",
        registerProcessor: "readonly",
        currentFrame: "readonly",
        currentTime: "readonly",
        sampleRate: "readonly",
      },
    },
  },
);
