import { IssuerUnavailable, NotListed } from "../errors.js";
import type { Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { dig, isObject, pyStr, truthy } from "../pyish.js";
import {
  HOLDINGS_TTL,
  INDEX_TTL,
  call,
  makeHolding,
  nowUtc,
  number,
  okJson,
  requireHoldings,
  type Issuer,
} from "./base.js";

const PRODUCTS_URL = "https://www.de.vanguard/professionell/anlageprodukte";
const GRAPHQL_URL = "https://www.de.vanguard/gpx/graphql";
const HEADERS = { "Content-Type": "application/json", "X-Consumer-ID": "de7" };
const MAX_PAGES = 20;

const FUNDS_QUERY =
  "query FundsQuery($portIds: [String!]!) { funds(portIds: $portIds) { portId profile " +
  '{ portId fundFullName fundCurrency identifiers(altIds: ["ISIN"]) ' +
  "{ altId altIdCode altIdValue } } } }";

const HOLDINGS_QUERY = `query FundsHoldingsQuery($portIds: [String!], $securityTypes: [String!], $lastItemKey: String) {
    funds(portIds: $portIds) {
      profile {
        fundFullName
        fundCurrency
        primarySectorEquityClassification
      }
    }
    borHoldings(portIds: $portIds) {
      holdings(limit: 1500, securityTypes: $securityTypes, lastItemKey: $lastItemKey) {
        items {
          issuerName
          securityLongDescription
          gicsSectorDescription
          icbSectorDescription
          icbIndustryDescription
          marketValuePercentage
          sedol1
          quantity
          ticker
          securityType
          finalMaturity
          effectiveDate
          marketValueBaseCurrency
          bloombergIsoCountry
          couponRate
        }
        totalHoldings
        lastItemKey
      }
    }
  }`;

const STATE = /<script id="serverApp-state"[^>]*>([\s\S]*?)<\/script>/;

type Obj = Record<string, unknown>;

/** Adapter for Vanguard UCITS ETFs and funds listed on the German site. */
export class VanguardIssuer implements Issuer {
  readonly name = "vanguard";

  private portIds(page: string): string[] {
    const match = STATE.exec(page);
    if (match === null) throw new IssuerUnavailable(this.name, "serverApp-state script not found");
    let ids: unknown;
    try {
      const state: unknown = JSON.parse(match[1]!);
      ids = dig(state, "_angular_initial_state", ":items", "root", ":items", "site-config", "portIds");
    } catch {
      throw new IssuerUnavailable(this.name, "portIds missing in the page state");
    }
    return pyStr(ids)
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part !== "");
  }

  private async graphql(
    http: Transport,
    operation: string,
    query: string,
    variables: Obj,
    ttl: number,
  ): Promise<[Obj, boolean]> {
    const body = { operationName: operation, variables, query };
    const answer = await call(this.name, http, "POST", GRAPHQL_URL, {
      json: body,
      headers: HEADERS,
      ttl,
    });
    const data = okJson(this.name, answer);
    if (!isObject(data) || truthy(data["errors"]) || !isObject(data["data"])) {
      throw new IssuerUnavailable(this.name, `GraphQL ${operation} answered with errors`);
    }
    return [data["data"], answer.stale];
  }

  /** Find the portfolio id of the ISIN, then page through its holdings. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const page = await call(this.name, http, "GET", PRODUCTS_URL, { ttl: INDEX_TTL });
    if (page.status !== 200) {
      throw new IssuerUnavailable(this.name, `HTTP ${page.status} from ${page.url}`);
    }
    const portIds = this.portIds(page.text);
    const [funds, fundsStale] = await this.graphql(
      http,
      "FundsQuery",
      FUNDS_QUERY,
      { portIds },
      INDEX_TTL,
    );
    let stale = fundsStale || page.stale;
    let portId: string | null = null;
    for (const fund of (truthy(funds["funds"]) ? funds["funds"] : []) as Obj[]) {
      const profile = fund["profile"];
      const identifiers = ((truthy(profile) ? (profile as Obj)["identifiers"] : undefined) ??
        []) as Obj[];
      if (identifiers.some((i) => i["altIdValue"] === isin)) {
        portId = pyStr(fund["portId"]);
        break;
      }
    }
    if (portId === null) throw new NotListed(this.name, isin, "not in the Vanguard fund list");

    const holdings: Holding[] = [];
    let profile: Obj = {};
    const dates: string[] = [];
    let key: unknown = null;
    let finished = false;
    for (let pageNo = 0; pageNo < MAX_PAGES; pageNo++) {
      const [data, pageStale] = await this.graphql(
        http,
        "FundsHoldingsQuery",
        HOLDINGS_QUERY,
        { portIds: [portId], lastItemKey: key },
        HOLDINGS_TTL,
      );
      stale = stale || pageStale;
      let items: Obj[];
      try {
        if (!truthy(profile)) profile = dig(data, "funds", 0, "profile") as Obj;
        const block = dig(data, "borHoldings", 0, "holdings") as Obj;
        items = dig(block, "items") as Obj[];
        key = block["lastItemKey"] ?? null;
      } catch {
        throw new IssuerUnavailable(this.name, "holdings path missing in the answer");
      }
      for (const item of items) {
        const weight = number(item["marketValuePercentage"]);
        const name = truthy(item["issuerName"]) ? item["issuerName"] : item["securityLongDescription"];
        if (weight === null || !truthy(name)) continue;
        if (truthy(item["effectiveDate"])) dates.push(pyStr(item["effectiveDate"]));
        holdings.push(
          makeHolding(pyStr(name), weight, {
            ticker: item["ticker"],
            country: item["bloombergIsoCountry"],
            sector: truthy(item["gicsSectorDescription"])
              ? item["gicsSectorDescription"]
              : item["icbSectorDescription"],
            asset_class: item["securityType"],
          }),
        );
      }
      if (!truthy(key)) {
        finished = true;
        break;
      }
    }
    if (!finished) {
      throw new IssuerUnavailable(this.name, `more than ${MAX_PAGES} pages of holdings`);
    }
    return {
      isin,
      issuer: this.name,
      fund_name: (profile["fundFullName"] ?? null) as string | null,
      as_of: dates.length > 0 ? dates.reduce((a, b) => (b > a ? b : a)) : null,
      currency: (profile["fundCurrency"] ?? null) as string | null,
      source_url: GRAPHQL_URL,
      fetched_at: nowUtc(),
      stale,
      holdings: requireHoldings(this.name, holdings),
    };
  }
}
