/** Map each issuer's own asset class label to the library's closed vocabulary. */

// Labels compared lower-cased, per issuer.
const EXACT: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  ishares: {
    equity: "equity",
    "fixed income": "fixed_income",
    "money market": "cash",
    cash: "cash",
    "cash collateral and margins": "cash",
    fx: "derivative",
    futures: "derivative",
    swaps: "derivative",
    derivative: "derivative",
    "real estate": "real_estate",
    commodity: "commodity",
  },
  xtrackers: {
    equities: "equity",
    equity: "equity",
    bonds: "fixed_income",
    "fixed income": "fixed_income",
    cash: "cash",
    currency: "cash",
    futures: "derivative",
    swaps: "derivative",
    forwards: "derivative",
    funds: "fund",
    "mutual fund": "fund",
  },
};

// Code prefixes compared upper-cased, per issuer, first match wins.
const PREFIX: Readonly<Record<string, ReadonlyArray<readonly [string, string]>>> = {
  vanguard: [
    ["EQ.REIT", "real_estate"],
    ["EQ.ETF", "fund"],
    ["EQ.", "equity"],
    ["MF.", "fund"],
    ["FI.", "fixed_income"],
    ["MM.", "cash"],
    ["CT.", "cash"],
    ["CRNY", "cash"],
    ["DE.", "derivative"],
  ],
  amundi: [
    ["EQUITY", "equity"],
    ["BOND", "fixed_income"],
    ["FIXED_INCOME", "fixed_income"],
    ["CASH", "cash"],
    ["CURRENCY", "cash"],
    ["FUTURE", "derivative"],
    ["SWAP", "derivative"],
    ["FORWARD", "derivative"],
    ["OPTION", "derivative"],
    ["DERIVATIVE", "derivative"],
    ["FUND", "fund"],
    ["ETF", "fund"],
  ],
};

/** The vocabulary value for an issuer's label: null when there is none, `other` if unknown. */
export function normalizeAssetClass(issuer: string, raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const label = raw.trim();
  if (label === "" || label === "-") return null;
  const table = Object.hasOwn(EXACT, issuer) ? EXACT[issuer]! : {};
  const lower = label.toLowerCase();
  if (Object.hasOwn(table, lower)) return table[lower]!;
  const upper = label.toUpperCase();
  for (const [prefix, value] of Object.hasOwn(PREFIX, issuer) ? PREFIX[issuer]! : []) {
    if (upper.startsWith(prefix)) return value;
  }
  return "other";
}
