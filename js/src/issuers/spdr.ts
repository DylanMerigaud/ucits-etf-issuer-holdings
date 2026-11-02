import { IssuerUnavailable, NotListed } from "../errors.js";
import type { Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { dig, pyRepr, pyStr, truthy } from "../pyish.js";
import { readSheet, XlsxError, type Cell } from "../xlsx.js";
import {
  HOLDINGS_TTL,
  INDEX_TTL,
  call,
  clean,
  makeHolding,
  nowUtc,
  number,
  okJson,
  requireHoldings,
  type Issuer,
} from "./base.js";

const FINDER_URL = "https://www.ssga.com/bin/v1/ssmp/fund/fundfinder";
const FINDER_PARAMS = {
  country: "de",
  language: "de",
  role: "individual",
  product: "etfs",
  ui: "fund-finder",
};
const HOLDINGS_URL =
  "https://www.ssga.com/library-content/products/fund-data/etfs/emea/holdings-daily-emea-en-{slug}.xlsx";

const KID_ISIN = /isin=([A-Z]{2}[A-Z0-9]{9}[0-9])/;
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** `SPYW GY` (or `SPYW GY^`) as `spyw-gy`. */
export function slugOf(ticker: string): string {
  return ticker.replace(/\^/g, "").trim().toLowerCase().replace(/ /g, "-");
}

/** `30-Oct-2026` as `2026-10-30`. */
function parseDate(text: unknown): string | null {
  const match = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec(truthy(text) ? pyStr(text).trim() : "");
  if (match === null) return null;
  const month = MONTHS.indexOf(match[2]!.toLowerCase());
  if (month === -1) return null;
  return `${match[3]}-${String(month + 1).padStart(2, "0")}-${String(Number(match[1])).padStart(2, "0")}`;
}

type Obj = Record<string, unknown>;

/** The (name, ticker) of the fund whose KID links carry this ISIN. */
function findFund(finder: unknown, isin: string): [string, string] | null {
  let funds: Obj[];
  try {
    funds = dig(finder, "data", "funds", "etfs", "datas") as Obj[];
  } catch {
    throw new IssuerUnavailable("spdr", "fund list path missing in the answer");
  }
  for (const fund of funds) {
    for (const group of (truthy(fund["documentPdf"]) ? fund["documentPdf"] : []) as Obj[]) {
      for (const doc of (truthy(group["docs"]) ? group["docs"] : []) as Obj[]) {
        const match = KID_ISIN.exec(truthy(doc["path"]) ? String(doc["path"]) : "");
        if (match !== null && match[1] === isin && truthy(fund["fundTicker"])) {
          return [truthy(fund["fundName"]) ? String(fund["fundName"]) : "", String(fund["fundTicker"])];
        }
      }
    }
  }
  return null;
}

/** Adapter for SPDR (State Street) UCITS ETFs. */
export class SpdrIssuer implements Issuer {
  readonly name = "spdr";

  /** Find the ticker of the ISIN in the fund finder, then read the holdings xlsx. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const finderAnswer = await call(this.name, http, "GET", FINDER_URL, {
      params: FINDER_PARAMS,
      ttl: INDEX_TTL,
    });
    const found = findFund(okJson(this.name, finderAnswer), isin);
    if (found === null) throw new NotListed(this.name, isin, "not in the SPDR fund list");
    const [listedName, ticker] = found;
    const url = HOLDINGS_URL.replace("{slug}", slugOf(ticker));
    const answer = await call(this.name, http, "GET", url, { ttl: HOLDINGS_TTL });
    if (answer.status !== 200) {
      throw new IssuerUnavailable(this.name, `HTTP ${answer.status} from ${url}`);
    }
    let rows: Cell[][];
    try {
      [, rows] = readSheet(answer.content);
    } catch (error) {
      if (error instanceof XlsxError) {
        throw new IssuerUnavailable(this.name, `holdings file is not an xlsx: ${error.message}`);
      }
      throw error;
    }

    const meta = new Map<string, Cell>();
    let headerAt = -1;
    for (let position = 0; position < rows.length; position++) {
      const row = rows[position]!;
      const label = row.length > 0 ? clean(row[0]) : null;
      if (label !== null && row.map(clean).includes("Percent of Fund")) {
        headerAt = position;
        break;
      }
      if (label !== null && label.endsWith(":") && row.length > 1) meta.set(label, row[1]!);
    }
    if (headerAt === -1) {
      throw new IssuerUnavailable(this.name, "header row with 'Percent of Fund' not found");
    }
    const header = rows[headerAt]!.map(clean);
    const indexOf = (label: string): number => {
      const where = header.indexOf(label);
      if (where === -1) throw new IssuerUnavailable(this.name, `expected column missing: ${pyRepr(label)} is not in list`);
      return where;
    };
    indexOf("ISIN");
    indexOf("Security Name");
    const weightAt = indexOf("Percent of Fund");
    const cell = (row: Cell[], label: string): Cell => {
      const where = header.indexOf(label);
      return where !== -1 && where < row.length ? row[where]! : null;
    };

    const holdings: Holding[] = [];
    for (const row of rows.slice(headerAt + 1)) {
      const weight = weightAt < row.length ? number(row[weightAt]) : null;
      if (weight === null) break;
      const name = cell(row, "Security Name");
      holdings.push(
        makeHolding(truthy(name) ? pyStr(name) : "", weight, {
          isin: cell(row, "ISIN"),
          country_name: cell(row, "Trade Country Name"),
          sector: cell(row, "Sector Classification"),
          currency: cell(row, "Currency"),
        }),
      );
    }
    return {
      isin,
      issuer: this.name,
      fund_name: clean(meta.get("Fund Name:")) ?? clean(listedName),
      as_of: parseDate(meta.get("Holdings As Of:")),
      currency: null,
      source_url: url,
      fetched_at: nowUtc(),
      stale: finderAnswer.stale || answer.stale,
      holdings: requireHoldings(this.name, holdings),
    };
  }
}
