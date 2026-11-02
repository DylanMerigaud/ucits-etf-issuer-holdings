import { ISO2_TO_NAME, NAME_TO_ISO2 } from "./countryData.js";

/** Return the alpha-2 code for a country name or code, or null when unknown. */
export function toIso2(text: string | null | undefined): string | null {
  if (!text) return null;
  const cleaned = text.trim();
  if ([...cleaned].length === 2 && /^\p{L}+$/u.test(cleaned)) {
    const code = cleaned.toUpperCase();
    return ISO2_TO_NAME.has(code) ? code : null;
  }
  return NAME_TO_ISO2.get(cleaned.toLowerCase()) ?? null;
}

/** Return the English country name for an alpha-2 code, or null when unknown. */
export function nameOf(code: string | null | undefined): string | null {
  if (!code) return null;
  return ISO2_TO_NAME.get(code.trim().toUpperCase()) ?? null;
}
