/* ============================================================================
   Language helpers (doc 01 §9 — Kannada is first-class). Script detection for
   the Ask DRISHTI composer's auto EN/KN mode. Mirrors the backend's
   nlsql.engine.detect_language so client and server agree on the asked language.
   ========================================================================== */

export type Lang = "en" | "kn";

/** Unicode block for Kannada (U+0C80–U+0CFF). */
const KANNADA = /[\u0c80-\u0cff]/;

export function hasKannada(text: string): boolean {
  return KANNADA.test(text ?? "");
}

/** Detect the script of a snippet: Kannada if any Kannada codepoint is present. */
export function detectLang(text: string): Lang {
  return hasKannada(text) ? "kn" : "en";
}

/** Human label for a language code. */
export function langLabel(lang: Lang): string {
  return lang === "kn" ? "ಕನ್ನಡ" : "English";
}
