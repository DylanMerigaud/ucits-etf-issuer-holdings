/** Small helpers that give JavaScript values the truthiness, string and rounding rules the Python
 * reference implementation relies on, so both ports read an issuer answer the same way. */

/** Python truthiness: null, false, 0, "", empty array and empty object are falsy. */
export function truthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === "number") return value !== 0 && !Number.isNaN(value);
  if (typeof value === "string") return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as object).length > 0;
  return true;
}

/** True for a plain JSON object (not null, not an array). */
export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Python `str()` for the JSON scalar types. */
export function pyStr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  return String(value);
}

/** Python `repr()` of a string: single quotes unless the text holds one and no double quote. */
export function pyRepr(text: string): string {
  const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
  const escaped = text
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t");
  return quote + (quote === "'" ? escaped.replace(/'/g, "\\'") : escaped) + quote;
}

/** Python `round(x, digits)`: correct rounding of the exact binary value. */
export function pyRound(value: number, digits: number): number {
  if (!Number.isFinite(value) || Math.abs(value) >= 1e21) return value;
  return Number(value.toFixed(digits));
}

/** Python `str(float)` (also what a CSV cell shows): `5.0`, `0.0001`, `1e-05`, `1e+16`. */
export function pyFloat(value: number): string {
  if (Number.isNaN(value)) return "nan";
  if (!Number.isFinite(value)) return value < 0 ? "-inf" : "inf";
  if (value === 0) return Object.is(value, -0) ? "-0.0" : "0.0";
  const [mantissa, exp] = value.toExponential().split("e") as [string, string];
  const e = Number(exp);
  const sign = mantissa.startsWith("-") ? "-" : "";
  const digits = mantissa.replace("-", "").replace(".", "");
  if (e < -4 || e >= 16) {
    const head = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    const abs = Math.abs(e);
    return `${sign}${head}e${e < 0 ? "-" : "+"}${abs < 10 ? "0" : ""}${abs}`;
  }
  if (e >= 0) {
    const int = digits.padEnd(e + 1, "0");
    const frac = digits.slice(e + 1);
    return `${sign}${int.slice(0, e + 1)}.${frac || "0"}`;
  }
  return `${sign}0.${"0".repeat(-e - 1)}${digits}`;
}

/** Python `f"{x:g}"` (six significant digits, trailing zeros dropped). */
export function pyG(value: number): string {
  if (Number.isNaN(value)) return "nan";
  if (!Number.isFinite(value)) return value < 0 ? "-inf" : "inf";
  if (value === 0) return Object.is(value, -0) ? "-0" : "0";
  const [mantissa, exp] = value.toExponential(5).split("e") as [string, string];
  const e = Number(exp);
  if (e < -4 || e >= 6) {
    const head = mantissa.includes(".") ? mantissa.replace(/\.?0+$/, "") : mantissa;
    const abs = Math.abs(e);
    return `${head}e${e < 0 ? "-" : "+"}${abs < 10 ? "0" : ""}${abs}`;
  }
  const fixed = value.toFixed(Math.max(0, 5 - e));
  return fixed.includes(".") ? fixed.replace(/\.?0+$/, "") : fixed;
}

/** Walk `keys` down `root` like Python `root[k1][k2]...`: throws when a key or index is missing. */
export function dig(root: unknown, ...keys: Array<string | number>): unknown {
  let node = root;
  for (const key of keys) {
    if (typeof key === "number") {
      if (!Array.isArray(node) || key >= node.length) throw new Error(`missing index ${key}`);
      node = node[key];
    } else {
      if (!isObject(node) || !(key in node)) throw new Error(`missing key ${key}`);
      node = node[key];
    }
  }
  return node;
}
