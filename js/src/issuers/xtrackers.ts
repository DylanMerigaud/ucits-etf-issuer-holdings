import { IssuerUnavailable, NotListed } from "../errors.js";
import type { HttpResponse, Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { pyRound } from "../pyish.js";
import { readSheet, XlsxError, type Cell } from "../xlsx.js";
import {
  HOLDINGS_TTL,
  clean,
  fetchParsed,
  fetchedAt,
  isoDate,
  makeHolding,
  number,
  requireHoldings,
  type Issuer,
} from "./base.js";

const URL = "https://etf.dws.com/etfdata/export/GBR/ENG/excel/product/constituent/{isin}/";

/** The holdings and the as-of date (the sheet name); an answer not an xlsx is NotListed. */
function parse(response: HttpResponse, isin: string): [Holding[], string | null] {
  if (!(response.content[0] === 0x50 && response.content[1] === 0x4b)) {
    throw new NotListed("xtrackers", isin, `no constituents file (HTTP ${response.status})`);
  }
  let sheetName: string;
  let rows: Cell[][];
  try {
    [sheetName, rows] = readSheet(response.content);
  } catch (error) {
    if (error instanceof XlsxError) {
      throw new IssuerUnavailable("xtrackers", `constituents file unreadable: ${error.message}`);
    }
    throw error;
  }
  const headerAt = rows.findIndex((row) => row.includes("Name") && row.includes("Weighting"));
  if (headerAt === -1) {
    throw new IssuerUnavailable("xtrackers", "header row with 'Name' and 'Weighting' not found");
  }
  const header = rows[headerAt]!;
  const column = (row: Cell[], label: string): Cell => {
    const where = header.indexOf(label);
    return where !== -1 && where < row.length ? row[where]! : null;
  };
  const holdings: Holding[] = [];
  for (const row of rows.slice(headerAt + 1)) {
    const fraction = number(column(row, "Weighting"));
    const name = clean(column(row, "Name"));
    if (fraction === null || name === null) continue;
    holdings.push(
      makeHolding(name, pyRound(fraction * 100, 10), {
        isin: column(row, "ISIN"),
        country_name: column(row, "Country"),
        sector: column(row, "Industry Classification"),
        currency: column(row, "Currency"),
        asset_class: column(row, "Type of Security"),
        issuer: "xtrackers",
      }),
    );
  }
  return [requireHoldings("xtrackers", holdings), isoDate(sheetName)];
}

/** Adapter for Xtrackers (DWS) UCITS ETFs. */
export class XtrackersIssuer implements Issuer {
  readonly name = "xtrackers";

  /** Download the constituents file; an answer that is not an xlsx means not listed. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const url = URL.replace("{isin}", isin);
    const [answer, [holdings, asOf]] = await fetchParsed(
      this.name,
      http,
      "GET",
      url,
      (response) => parse(response, isin),
      { ttl: HOLDINGS_TTL },
    );
    return {
      isin,
      issuer: this.name,
      fund_name: null,
      as_of: asOf,
      currency: null,
      source_url: url,
      fetched_at: fetchedAt(answer),
      stale: answer.stale,
      holdings,
    };
  }
}
