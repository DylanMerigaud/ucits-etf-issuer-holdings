import { IssuerUnavailable, NotListed } from "../errors.js";
import type { HttpResponse, Transport } from "../http.js";
import type { Fund, Holding } from "../models.js";
import { isObject, pyStr, truthy } from "../pyish.js";
import {
  HOLDINGS_TTL,
  INDEX_TTL,
  asDict,
  fetchParsed,
  fetchedAt,
  isoDate,
  makeHolding,
  number,
  okJson,
  requireOk,
  requireHoldings,
  text,
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

/** The portfolio ids listed in the fund list page's state script. */
function parsePage(response: HttpResponse): string[] {
  requireOk("vanguard", response);
  const match = STATE.exec(response.text);
  if (match === null) throw new IssuerUnavailable("vanguard", "serverApp-state script not found");
  let node: unknown;
  try {
    node = JSON.parse(match[1]!);
  } catch {
    throw new IssuerUnavailable("vanguard", "portIds missing in the page state");
  }
  for (const key of ["_angular_initial_state", ":items", "root", ":items", "site-config", "portIds"]) {
    node = isObject(node) ? node[key] : undefined;
  }
  const ids =
    typeof node === "string"
      ? node
          .split(",")
          .map((part) => part.trim())
          .filter((part) => part !== "")
      : [];
  if (ids.length === 0) throw new IssuerUnavailable("vanguard", "portIds missing in the page state");
  return ids;
}

function graphqlData(response: HttpResponse, operation: string): Obj {
  const data = okJson("vanguard", response);
  if (!isObject(data) || truthy(data["errors"]) || !isObject(data["data"])) {
    throw new IssuerUnavailable("vanguard", `GraphQL ${operation} answered with errors`);
  }
  return data["data"];
}

function parseFunds(response: HttpResponse): unknown[] {
  const funds = graphqlData(response, "FundsQuery")["funds"];
  if (!Array.isArray(funds)) {
    throw new IssuerUnavailable("vanguard", "funds missing in the FundsQuery answer");
  }
  return funds;
}

/** The portId of the fund whose identifiers carry this ISIN, null when no fund does. */
function portIdOf(funds: unknown[], isin: string): string | null {
  for (const fund of funds) {
    if (!isObject(fund)) continue;
    const identifiers = asDict(fund["profile"])["identifiers"];
    if (!Array.isArray(identifiers)) continue;
    if (identifiers.some((i) => isObject(i) && i["altIdValue"] === isin)) {
      const portId = fund["portId"];
      const usable =
        (typeof portId === "string" || (typeof portId === "number" && Number.isInteger(portId))) &&
        String(portId).trim() !== "";
      if (!usable) throw new IssuerUnavailable("vanguard", "portId missing for the fund");
      return String(portId);
    }
  }
  return null;
}

interface Page {
  profile: Obj;
  holdings: Holding[];
  dates: string[];
  key: unknown;
}

function parseHoldings(response: HttpResponse): Page {
  const data = graphqlData(response, "FundsHoldingsQuery");
  const funds = data["funds"];
  const first = Array.isArray(funds) && funds.length > 0 ? asDict(funds[0]) : {};
  const blocks = data["borHoldings"];
  const block = Array.isArray(blocks) && blocks.length > 0 ? asDict(blocks[0])["holdings"] : undefined;
  const items = isObject(block) ? block["items"] : undefined;
  if (!isObject(block) || !Array.isArray(items)) {
    throw new IssuerUnavailable("vanguard", "holdings path missing in the answer");
  }
  const holdings: Holding[] = [];
  const dates: string[] = [];
  for (const item of items) {
    if (!isObject(item)) continue;
    const weight = number(item["marketValuePercentage"]);
    const name = truthy(item["issuerName"]) ? item["issuerName"] : item["securityLongDescription"];
    if (weight === null || !truthy(name)) continue;
    const date = isoDate(item["effectiveDate"]);
    if (date !== null) dates.push(date);
    holdings.push(
      makeHolding(pyStr(name), weight, {
        ticker: item["ticker"],
        country: item["bloombergIsoCountry"],
        sector: truthy(item["gicsSectorDescription"])
          ? item["gicsSectorDescription"]
          : item["icbSectorDescription"],
        asset_class: item["securityType"],
        issuer: "vanguard",
      }),
    );
  }
  return { profile: asDict(first["profile"]), holdings, dates, key: block["lastItemKey"] ?? null };
}

/** Adapter for Vanguard UCITS ETFs and funds listed on the German site. */
export class VanguardIssuer implements Issuer {
  readonly name = "vanguard";

  private graphql<T>(
    http: Transport,
    operation: string,
    query: string,
    variables: Obj,
    ttl: number,
    parse: (response: HttpResponse) => T,
  ): Promise<[HttpResponse, T]> {
    const body = { operationName: operation, variables, query };
    return fetchParsed(this.name, http, "POST", GRAPHQL_URL, parse, { json: body, headers: HEADERS, ttl });
  }

  /** Find the portfolio id of the ISIN, then page through its holdings. */
  async fetch(isin: string, http: Transport): Promise<Fund> {
    const [page, portIds] = await fetchParsed(this.name, http, "GET", PRODUCTS_URL, parsePage, {
      ttl: INDEX_TTL,
    });
    const [fundsAnswer, funds] = await this.graphql(
      http,
      "FundsQuery",
      FUNDS_QUERY,
      { portIds },
      INDEX_TTL,
      parseFunds,
    );
    const portId = portIdOf(funds, isin);
    if (portId === null) throw new NotListed(this.name, isin, "not in the Vanguard fund list");

    const answers = [page, fundsAnswer];
    const holdings: Holding[] = [];
    let profile: Obj = {};
    const dates: string[] = [];
    let key: unknown = null; // sent back exactly as the previous page returned it
    let finished = false;
    for (let pageNo = 0; pageNo < MAX_PAGES; pageNo++) {
      const [answer, parsed] = await this.graphql(
        http,
        "FundsHoldingsQuery",
        HOLDINGS_QUERY,
        { portIds: [portId], lastItemKey: key },
        HOLDINGS_TTL,
        parseHoldings,
      );
      answers.push(answer);
      if (!truthy(profile)) profile = parsed.profile;
      holdings.push(...parsed.holdings);
      dates.push(...parsed.dates);
      key = parsed.key;
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
      fund_name: text(profile["fundFullName"]),
      as_of: dates.length > 0 ? dates.reduce((a, b) => (b > a ? b : a)) : null,
      currency: text(profile["fundCurrency"]),
      source_url: GRAPHQL_URL,
      fetched_at: fetchedAt(...answers),
      stale: answers.some((a) => a.stale),
      holdings: requireHoldings(this.name, holdings),
    };
  }
}
