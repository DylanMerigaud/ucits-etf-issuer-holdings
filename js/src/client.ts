import { FundNotFound, IssuerUnavailable, NotListed } from "./errors.js";
import { CachingTransport, DEFAULT_CACHE_DIR, FetchTransport, type Transport } from "./http.js";
import { normalizeIsin } from "./isin.js";
import { ISSUERS, ISSUER_ORDER } from "./issuers/index.js";
import type { Fund } from "./models.js";
import { pyRepr } from "./pyish.js";

/** Options of {@link HoldingsClient}. */
export interface ClientOptions {
  /** A transport to use instead of `fetch`; used as it is unless you also pass `cacheDir`. */
  transport?: Transport;
  /** Directory of the on-disk cache. Default: the user cache dir (only with the default transport). `null` disables the cache. */
  cacheDir?: string | null;
  /** Issuer names to ask, in this order. Default: all six. */
  issuers?: readonly string[];
  /** Request timeout in milliseconds for the default transport. Default 30000. */
  timeoutMs?: number;
}

/** Options of {@link HoldingsClient.get}. */
export interface GetOptions {
  /** Ask only this issuer. */
  issuer?: string;
}

/** Fetches the holdings an issuer publishes for an ISIN. */
export class HoldingsClient {
  private readonly names: readonly string[];
  private readonly http: Transport;

  /** @throws {Error} when an issuer name is unknown. */
  constructor(options: ClientOptions = {}) {
    const names = options.issuers !== undefined ? [...options.issuers] : [...ISSUER_ORDER];
    const unknown = names.filter((name) => !(name in ISSUERS));
    if (unknown.length > 0) throw new Error(`unknown issuer(s): ${unknown.join(", ")}`);
    this.names = names;
    const { transport, cacheDir } = options;
    const base = transport ?? new FetchTransport(options.timeoutMs ?? 30_000);
    const dir = cacheDir === undefined ? (transport === undefined ? DEFAULT_CACHE_DIR : null) : cacheDir;
    this.http = dir !== null ? new CachingTransport(base, dir) : base;
  }

  /**
   * Return the fund for `isin`, asking only `opts.issuer` when given.
   *
   * @throws {InvalidISIN} for a malformed ISIN.
   * @throws {Error} for an unknown issuer name.
   * @throws {FundNotFound} when no issuer answered with holdings.
   */
  async get(isin: string, opts: GetOptions = {}): Promise<Fund> {
    const code = normalizeIsin(isin);
    let names: readonly string[];
    if (opts.issuer !== undefined) {
      if (!(opts.issuer in ISSUERS)) throw new Error(`unknown issuer: ${pyRepr(opts.issuer)}`);
      names = [opts.issuer];
    } else {
      names = this.names;
    }
    const reasons: Record<string, string> = {};
    for (const name of names) {
      try {
        return await ISSUERS[name]!.fetch(code, this.http);
      } catch (error) {
        if (error instanceof NotListed || error instanceof IssuerUnavailable) {
          reasons[name] = error.reason;
          continue;
        }
        throw error;
      }
    }
    throw new FundNotFound(code, reasons);
  }
}

/** Options of {@link getHoldings}. */
export interface GetHoldingsOptions extends ClientOptions, GetOptions {}

/** One-call form of `new HoldingsClient(options).get(isin, { issuer })`. */
export function getHoldings(isin: string, opts: GetHoldingsOptions = {}): Promise<Fund> {
  const { issuer, ...clientOptions } = opts;
  return new HoldingsClient(clientOptions).get(isin, issuer !== undefined ? { issuer } : {});
}
