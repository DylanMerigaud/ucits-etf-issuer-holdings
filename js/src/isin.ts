import { InvalidISIN } from "./errors.js";
import { pyRepr } from "./pyish.js";

const SHAPE = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;

function luhnOk(isin: string): boolean {
  const digits = [...isin].map((ch) => String(parseInt(ch, 36))).join("");
  let total = 0;
  const reversed = [...digits].reverse();
  reversed.forEach((ch, index) => {
    let value = Number(ch);
    if (index % 2 === 1) {
      value *= 2;
      if (value > 9) value -= 9;
    }
    total += value;
  });
  return total % 10 === 0;
}

/**
 * Return the ISIN stripped and upper-cased.
 *
 * @throws {InvalidISIN} when the text is not a string, not ISIN-shaped, or has a bad check digit.
 */
export function normalizeIsin(isin: string): string {
  if (typeof isin !== "string") {
    const kind = isin === null ? "NoneType" : typeof isin;
    throw new InvalidISIN(`ISIN must be a string, got ${kind}`);
  }
  const text = isin.trim().toUpperCase();
  if (!SHAPE.test(text)) throw new InvalidISIN(`not an ISIN: ${pyRepr(isin)}`);
  if (!luhnOk(text)) throw new InvalidISIN(`bad check digit: ${pyRepr(isin)}`);
  return text;
}
