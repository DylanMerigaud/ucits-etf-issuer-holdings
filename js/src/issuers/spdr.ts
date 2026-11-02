import { IssuerUnavailable, NotListed } from "../errors.js";
import type { HttpResponse, Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { isObject, pyRepr, pyStr, truthy } from "../pyish.js";
import { readSheet, XlsxError, type Cell } from "../xlsx.js";
import {
  HOLDINGS_TTL,
  INDEX_TTL,
  asList,
  clean,
  fetchParsed,
  fetchedAt,
  makeHolding,
  number,
  okJson,
  requireOk,
  requireHoldings,
  text,
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
function parseDate(value: unknown): string | null {
  const match = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec(truthy(value) ? pyStr(value).trim() : "");
  if (match === null) return null;
  const month = MONTHS.indexOf(match[2]!.toLowerCase());
  if (month === -1) return null;
  return `${match[3]}-${String(month + 1).padStart(2, "0")}-${String(Number(match[1])).padStart(2, "0")}`;
}

/** The fund entries of the fund finder answer. */
function parseFinder(response: HttpResponse): unknown[] {
  let node: unknown = okJson("spdr", response);
  for (const key of ["data", "funds", "etfs", "datas"]) node = isObject(node) ? node[key] : undefined;
  if (!Array.isArray(node)) throw new IssuerUnavailable("spdr", "fund list path missing in the answer");
  return node;
}

/** The (name, ticker) of the fund whose KID links carry this ISIN. */
function findFund(funds: unknown[], isin: string): [string | null, string] | null {
  for (const fund of funds) {
    if (!isObject(fund)) continue;
    const ticker = text(fund["fundTicker"]);
    for (const group of asList(fund["documentPdf"])) {
      const docs = isObject(group) ? group["docs"] : undefined;
      for (const doc of asList(docs)) {
        const path = isObject(doc) ? doc["path"] : undefined;
        const match = typeof path === "string" ? KID_ISIN.exec(path) : null;
        if (match !== null && match[1] === isin && ticker !== null) {
          return [text(fund["fundName"]), ticker];
        }
      }
    }
  }
  return null;
}

/** The labelled cells above the table (`Fund Name:` ...) and the holdings. */
function parseHoldings(response: HttpResponse): [Map<string, Cell>, Holding[]] {
  requireOk("spdr", response);
  let rows: Cell[][];
  try {
    [, rows] = readSheet(response.content);
  } catch (error) {
    if (error instanceof XlsxError) {
      throw new IssuerUnavailable("spdr", `holdings file is not an xlsx: ${error.message}`);
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
    throw new IssuerUnavailable("spdr", "header row with 'Percent of Fund' not found");
  }
  const header = rows[headerAt]!.map(clean);
  for (const label of ["ISIN", "Security Name"]) {
    if (!header.includes(label)) {
      throw new IssuerUnavailable("spdr", `expected column missing: ${pyRepr(label)} is not in list`);
    }
  }
  const weightAt = header.indexOf("Percent of Fund");
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
  return [meta, requireHoldings("spdr", holdings)];
}

/** Adapter for SPDR (State Street) UCITS ETFs. */
export class SpdrIssuer implements Issuer {
  readonly name = "spdr";

  /** Find the ticker of the ISIN in the fund finder, then read the holdings xlsx. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const [finderAnswer, funds] = await fetchParsed(this.name, http, "GET", FINDER_URL, parseFinder, {
      params: FINDER_PARAMS,
      ttl: INDEX_TTL,
    });
    const found = findFund(funds, isin);
    if (found === null) throw new NotListed(this.name, isin, "not in the SPDR fund list");
    const [listedName, ticker] = found;
    const url = HOLDINGS_URL.replace("{slug}", slugOf(ticker));
    const [answer, [meta, holdings]] = await fetchParsed(this.name, http, "GET", url, parseHoldings, {
      ttl: HOLDINGS_TTL,
    });
    return {
      isin,
      issuer: this.name,
      fund_name: text(meta.get("Fund Name:")) ?? listedName,
      as_of: parseDate(meta.get("Holdings As Of:")),
      currency: null,
      source_url: url,
      fetched_at: fetchedAt(finderAnswer, answer),
      stale: finderAnswer.stale || answer.stale,
      holdings,
    };
  }
}
