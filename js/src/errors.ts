/** Errors raised by the library. All of them extend {@link HoldingsError}. */

/** Base class of every error raised by this library. */
export class HoldingsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** The text is not a valid ISIN (shape or check digit). */
export class InvalidISIN extends HoldingsError {}

/** A request failed before any answer came back (network, timeout, TLS). */
export class TransportError extends HoldingsError {}

/** The issuer does not list this ISIN. */
export class NotListed extends HoldingsError {
  readonly issuer: string;
  readonly isin: string;
  readonly reason: string;

  constructor(issuer: string, isin: string, reason = "not listed") {
    super(`${issuer}: ${isin}: ${reason}`);
    this.issuer = issuer;
    this.isin = isin;
    this.reason = reason;
  }
}

/** The issuer did not answer, or answered in a shape this library does not know. */
export class IssuerUnavailable extends HoldingsError {
  readonly issuer: string;
  readonly reason: string;

  constructor(issuer: string, reason: string) {
    super(`${issuer}: ${reason}`);
    this.issuer = issuer;
    this.reason = reason;
  }
}

/**
 * The issuer's site refused this network address (HTTP 403 before any data).
 *
 * iShares (BlackRock) serves its site through Akamai, which refuses most cloud and datacenter
 * address ranges whatever the request looks like, so the same call that works from a home
 * connection fails from a server or a CI runner. `url` is the address that refused.
 */
export class AccessDenied extends IssuerUnavailable {
  readonly url: string;

  constructor(issuer: string, url: string) {
    super(
      issuer,
      `HTTP 403 from ${url}: the site refused this network address (its CDN blocks most ` +
        "cloud and datacenter IP ranges, whatever the request headers); run from a " +
        "residential connection or send the requests through a proxy on one (README, " +
        "'Blocked by an issuer')",
    );
    this.url = url;
  }
}

/**
 * No issuer answered with holdings; `reasons` says why each one did not.
 *
 * `blocked` names the issuers that refused this network address ({@link AccessDenied}): the
 * fund may be theirs, the library could not ask.
 */
export class FundNotFound extends HoldingsError {
  readonly isin: string;
  readonly reasons: Record<string, string>;
  readonly blocked: readonly string[];

  constructor(isin: string, reasons: Record<string, string>, blocked: readonly string[] = []) {
    const detail = Object.entries(reasons)
      .map(([name, why]) => `${name}: ${why}`)
      .join("; ");
    const lead = blocked.length > 0
      ? `${isin}: no issuer returned holdings, and ${blocked.join(", ")} refused this network ` +
        "address, so the fund may be theirs"
      : `${isin}: no issuer returned holdings`;
    super(`${lead} (${detail})`);
    this.isin = isin;
    this.reasons = reasons;
    this.blocked = blocked;
  }
}
