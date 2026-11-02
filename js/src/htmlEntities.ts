/** HTML entity decoding for names that issuers publish with entities in them (Invesco). */

// The HTML 4 Latin-1 names (valid with or without the closing semicolon) ...
const LATIN1 =
  "nbsp iexcl cent pound curren yen brvbar sect uml copy ordf laquo not shy reg macr deg plusmn " +
  "sup2 sup3 acute micro para middot cedil sup1 ordm raquo frac14 frac12 frac34 iquest Agrave " +
  "Aacute Acirc Atilde Auml Aring AElig Ccedil Egrave Eacute Ecirc Euml Igrave Iacute Icirc Iuml " +
  "ETH Ntilde Ograve Oacute Ocirc Otilde Ouml times Oslash Ugrave Uacute Ucirc Uuml Yacute THORN " +
  "szlig agrave aacute acirc atilde auml aring aelig ccedil egrave eacute ecirc euml igrave " +
  "iacute icirc iuml eth ntilde ograve oacute ocirc otilde ouml divide oslash ugrave uacute ucirc " +
  "uuml yacute thorn yuml";

const LEGACY = new Map<string, string>([
  ["amp", "&"],
  ["lt", "<"],
  ["gt", ">"],
  ["quot", '"'],
]);
LATIN1.split(" ").forEach((name, i) => LEGACY.set(name, String.fromCharCode(160 + i)));

// ... and a few that only exist with the semicolon (name, code point).
const SEMI_ONLY = new Map<string, string>(
  (
    [
      ["apos", 0x27],
      ["euro", 0x20ac],
      ["hellip", 0x2026],
      ["ndash", 0x2013],
      ["mdash", 0x2014],
      ["lsquo", 0x2018],
      ["rsquo", 0x2019],
      ["sbquo", 0x201a],
      ["ldquo", 0x201c],
      ["rdquo", 0x201d],
      ["bdquo", 0x201e],
      ["bull", 0x2022],
      ["trade", 0x2122],
      ["dagger", 0x2020],
      ["Dagger", 0x2021],
      ["permil", 0x2030],
      ["lsaquo", 0x2039],
      ["rsaquo", 0x203a],
      ["OElig", 0x152],
      ["oelig", 0x153],
      ["Scaron", 0x160],
      ["scaron", 0x161],
      ["Yuml", 0x178],
      ["fnof", 0x192],
      ["circ", 0x2c6],
      ["tilde", 0x2dc],
      ["ensp", 0x2002],
      ["emsp", 0x2003],
      ["thinsp", 0x2009],
      ["zwnj", 0x200c],
      ["zwj", 0x200d],
      ["larr", 0x2190],
      ["rarr", 0x2192],
      ["uarr", 0x2191],
      ["darr", 0x2193],
      ["infin", 0x221e],
      ["ne", 0x2260],
      ["le", 0x2264],
      ["ge", 0x2265],
      ["minus", 0x2212],
    ] as Array<[string, number]>
  ).map(([name, code]) => [name, String.fromCodePoint(code)]),
);

// Python maps the C1 range of numeric references through windows-1252 (code points 0x80 to 0x9f).
const CP1252 = [
  0x20ac, 0x81, 0x201a, 0x192, 0x201e, 0x2026, 0x2020, 0x2021, 0x2c6, 0x2030, 0x160, 0x2039, 0x152,
  0x8d, 0x17d, 0x8f, 0x90, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x2dc, 0x2122,
  0x161, 0x203a, 0x153, 0x9d, 0x17e, 0x178,
];

function numeric(code: number): string {
  if (code === 0x0d) return "\r";
  if (code >= 0x80 && code <= 0x9f) return String.fromCodePoint(CP1252[code - 0x80]!);
  if (code === 0 || (code >= 0xd800 && code <= 0xdfff) || code > 0x10ffff) return "�";
  if ((code >= 0x1 && code <= 0x8) || code === 0xb || (code >= 0xe && code <= 0x1f)) return "";
  if (code === 0x7f) return "";
  if ((code >= 0xfdd0 && code <= 0xfdef) || (code & 0xfffe) === 0xfffe) return "";
  return String.fromCodePoint(code);
}

/** Decode HTML character references (`&amp;`, `&#39;`, `&eacute;`), like Python `html.unescape`. */
export function unescapeHtml(text: string): string {
  if (!text.includes("&")) return text;
  return text.replace(
    /&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)/g,
    (whole, body: string) => {
      if (body.startsWith("#")) {
        const hex = body[1] === "x" || body[1] === "X";
        const digits = body.slice(hex ? 2 : 1).replace(/;$/, "");
        return numeric(parseInt(digits, hex ? 16 : 10));
      }
      const semi = body.endsWith(";");
      const name = semi ? body.slice(0, -1) : body;
      if (semi) {
        const full = LEGACY.get(name) ?? SEMI_ONLY.get(name);
        if (full !== undefined) return full;
      }
      for (let x = name.length; x > 1; x--) {
        const legacy = LEGACY.get(name.slice(0, x));
        if (legacy !== undefined) return legacy + name.slice(x) + (semi ? ";" : "");
      }
      return whole;
    },
  );
}
