import { AmundiIssuer } from "./amundi.js";
import type { Issuer } from "./base.js";
import { InvescoIssuer } from "./invesco.js";
import { ISharesIssuer } from "./ishares.js";
import { SpdrIssuer } from "./spdr.js";
import { VanguardIssuer } from "./vanguard.js";
import { XtrackersIssuer } from "./xtrackers.js";

/** The issuer adapters by name. */
export const ISSUERS: Readonly<Record<string, Issuer>> = {
  ishares: new ISharesIssuer(),
  vanguard: new VanguardIssuer(),
  spdr: new SpdrIssuer(),
  xtrackers: new XtrackersIssuer(),
  amundi: new AmundiIssuer(),
  invesco: new InvescoIssuer(),
};

/** The order the client asks the issuers: the ones with a cached index first, then by ISIN. */
export const ISSUER_ORDER: readonly string[] = [
  "ishares",
  "vanguard",
  "spdr",
  "xtrackers",
  "amundi",
  "invesco",
];

export type { Issuer };
