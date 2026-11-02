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

/** No issuer answered with holdings; `reasons` says why each one did not. */
export class FundNotFound extends HoldingsError {
  readonly isin: string;
  readonly reasons: Record<string, string>;

  constructor(isin: string, reasons: Record<string, string>) {
    const detail = Object.entries(reasons)
      .map(([name, why]) => `${name}: ${why}`)
      .join("; ");
    super(`${isin}: no issuer returned holdings (${detail})`);
    this.isin = isin;
    this.reasons = reasons;
  }
}
