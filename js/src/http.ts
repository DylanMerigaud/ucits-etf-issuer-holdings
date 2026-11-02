import { createHash } from "node:crypto";
import { randomBytes } from "node:crypto";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { TransportError } from "./errors.js";
import { VERSION } from "./version.js";

/** The user agent sent with every request. */
export const USER_AGENT = `ucits-etf-issuer-holdings/${VERSION} (+https://github.com/DylanMerigaud/ucits-etf-issuer-holdings)`;

/** The default cache directory: `$XDG_CACHE_HOME` or `~/.cache`, then `ucits-etf-issuer-holdings`. */
export const DEFAULT_CACHE_DIR = join(
  process.env["XDG_CACHE_HOME"] || join(homedir(), ".cache"),
  "ucits-etf-issuer-holdings",
);

/**
 * What a transport returns: status, raw body, content type, final url.
 *
 * `storedAt` is when the body was fetched from the issuer, in seconds since the epoch (UTC):
 * now for a live answer, the time it was stored for a cached or stale copy.
 */
export class HttpResponse {
  readonly status: number;
  readonly content: Uint8Array;
  readonly contentType: string;
  readonly url: string;
  readonly stale: boolean;
  readonly storedAt: number;

  constructor(
    status: number,
    content: Uint8Array,
    contentType: string,
    url: string,
    stale = false,
    storedAt: number = Date.now() / 1000,
  ) {
    this.status = status;
    this.content = content;
    this.contentType = contentType;
    this.url = url;
    this.stale = stale;
    this.storedAt = storedAt;
  }

  /** The body decoded as UTF-8 (a leading byte order mark is dropped). */
  get text(): string {
    return new TextDecoder("utf-8").decode(this.content);
  }

  /** The body parsed as JSON. Throws a SyntaxError when it is not JSON. */
  json(): unknown {
    return JSON.parse(this.text);
  }

  /** The same response with some fields replaced. */
  with(changes: { content?: Uint8Array; stale?: boolean; status?: number }): HttpResponse {
    return new HttpResponse(
      changes.status ?? this.status,
      changes.content ?? this.content,
      this.contentType,
      this.url,
      changes.stale ?? this.stale,
      this.storedAt,
    );
  }
}

/** Options of one request. */
export interface RequestOptions {
  /** Query string parameters. */
  params?: Record<string, string> | null;
  /** A JSON body (the request is sent as JSON). */
  json?: unknown;
  headers?: Record<string, string> | null;
  /** Seconds a caching layer may keep the answer; null or absent means no caching. */
  ttl?: number | null;
  /**
   * Parses a new 200 answer and throws when it cannot. A caching layer keeps the answer only
   * when this returns; other transports ignore it.
   */
  validate?: ((response: HttpResponse) => unknown) | null;
}

/** Anything that can perform a request and return an {@link HttpResponse}. */
export interface Transport {
  /** Perform the request. A network failure rejects with {@link TransportError}. */
  request(method: string, url: string, options?: RequestOptions): Promise<HttpResponse>;
}

/** Append query parameters to a url, encoded like a form. */
export function withParams(url: string, params: Record<string, string> | null | undefined): string {
  if (!params || Object.keys(params).length === 0) return url;
  const query = new URLSearchParams(params).toString();
  return url + (url.includes("?") ? "&" : "?") + query;
}

/** Real network transport on the global `fetch`. Proxy support is whatever your Node gives fetch. */
export class FetchTransport implements Transport {
  private readonly timeoutMs: number;

  constructor(timeoutMs = 30_000) {
    this.timeoutMs = timeoutMs;
  }

  /** Send the request with the library's user agent; network errors become TransportError. */
  async request(
    method: string,
    url: string,
    options: RequestOptions = {},
  ): Promise<HttpResponse> {
    const headers: Record<string, string> = { "User-Agent": USER_AGENT, ...(options.headers ?? {}) };
    let body: string | undefined;
    if (options.json !== undefined && options.json !== null) {
      body = JSON.stringify(options.json);
      if (!Object.keys(headers).some((k) => k.toLowerCase() === "content-type")) {
        headers["Content-Type"] = "application/json";
      }
    }
    try {
      const answer = await fetch(withParams(url, options.params), {
        method,
        headers,
        body,
        redirect: "follow",
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      const content = new Uint8Array(await answer.arrayBuffer());
      return new HttpResponse(
        answer.status,
        content,
        answer.headers.get("content-type") ?? "",
        answer.url || url,
      );
    } catch (error) {
      const cause = error instanceof Error ? (error.cause as Error | undefined) : undefined;
      const detail = error instanceof Error ? error.message : String(error);
      throw new TransportError(`${method} ${url}: ${cause?.message ?? detail}`);
    }
  }
}

/** Python `json.dumps` with `ensure_ascii`, so cache keys match the Python package's. */
function pyDumps(value: unknown, sortKeys: boolean, compact: boolean): string {
  const sep = compact ? ["," , ":"] : [", ", ": "];
  const dump = (v: unknown): string => {
    if (v === null || v === undefined) return "null";
    if (typeof v === "string") {
      return JSON.stringify(v).replace(/[\u007f-￿]/g, (c) =>
        c === "\u007f" ? c : `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
      );
    }
    if (Array.isArray(v)) return `[${v.map(dump).join(sep[0])}]`;
    if (typeof v === "object") {
      let entries = Object.entries(v as Record<string, unknown>);
      if (sortKeys) entries = entries.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
      return `{${entries.map(([k, x]) => `${dump(k)}${sep[1]}${dump(x)}`).join(sep[0])}}`;
    }
    return JSON.stringify(v);
  };
  return dump(value);
}

/** Statuses after which a stale copy is served when one exists: refused, timed out, rate limited. */
const STALE_ON = new Set([403, 408, 429]);

/**
 * Wraps a transport with an on-disk cache of 200 answers.
 *
 * A copy younger than `ttl` is returned without a request. When the live request fails with a
 * {@link TransportError}, or answers 403, 408, 429 or 500 and above, and an older copy exists,
 * that copy is returned with `stale` set.
 *
 * A new 200 answer is kept only when `validate` (if given) accepts it. When it throws, the
 * previous copy stays in the cache and is returned with `stale` set; with no previous copy the
 * live answer is returned uncached.
 *
 * Each key is one file, `<sha256>.cache`: a JSON line of metadata, then the body, written to a
 * temporary file and renamed into place. Concurrent identical requests share one download. The
 * cache files are the same as the Python package writes.
 */
export class CachingTransport implements Transport {
  private readonly inner: Transport;
  private readonly dir: string;
  private readonly clock: () => number;
  private readonly inFlight = new Map<string, Promise<HttpResponse>>();

  /**
   * @param inner the transport asked on a miss
   * @param cacheDir directory holding the cache files
   * @param clock current time in seconds (replaceable for tests)
   */
  constructor(inner: Transport, cacheDir: string, clock: () => number = () => Date.now() / 1000) {
    this.inner = inner;
    this.dir = cacheDir;
    this.clock = clock;
  }

  private static key(
    method: string,
    url: string,
    params: Record<string, string> | null | undefined,
    body: unknown,
  ): string {
    const items = Object.entries(params ?? {}).sort(([a, x], [b, y]) =>
      a === b ? (x < y ? -1 : x > y ? 1 : 0) : a < b ? -1 : 1,
    );
    const parts = [
      method.toUpperCase(),
      url,
      pyDumps(items, false, false),
      pyDumps(body ?? null, true, true),
    ];
    return createHash("sha256").update(parts.join("\n"), "utf8").digest("hex");
  }

  private async load(key: string): Promise<HttpResponse | null> {
    let raw: Buffer;
    try {
      raw = await readFile(join(this.dir, `${key}.cache`));
    } catch {
      return null;
    }
    const cut = raw.indexOf(0x0a);
    if (cut === -1) return null;
    try {
      const meta = JSON.parse(raw.subarray(0, cut).toString("utf8")) as Record<string, unknown>;
      const storedAt = Number(meta["stored_at"]);
      const contentType = meta["content_type"];
      const url = meta["url"];
      if (meta["stored_at"] === null || typeof meta["stored_at"] === "boolean") return null;
      if (!Number.isFinite(storedAt) || typeof contentType !== "string" || typeof url !== "string") {
        return null;
      }
      return new HttpResponse(200, new Uint8Array(raw.subarray(cut + 1)), contentType, url, false, storedAt);
    } catch {
      return null;
    }
  }

  private async store(key: string, response: HttpResponse): Promise<void> {
    const meta = {
      stored_at: this.clock(),
      content_type: response.contentType,
      url: response.url,
    };
    const data = Buffer.concat([Buffer.from(pyDumps(meta, false, false) + "\n", "utf8"), response.content]);
    const temp = join(this.dir, `${key}.${randomBytes(6).toString("hex")}.tmp`);
    try {
      await mkdir(this.dir, { recursive: true });
      await writeFile(temp, data);
      await rename(temp, join(this.dir, `${key}.cache`));
    } catch {
      await rm(temp, { force: true }).catch(() => undefined);
      // a cache that cannot be written is not an error
    }
  }

  /** Serve from cache when fresh, else ask the inner transport, falling back to a stale copy. */
  async request(
    method: string,
    url: string,
    options: RequestOptions = {},
  ): Promise<HttpResponse> {
    const ttl = options.ttl ?? null;
    if (ttl === null) return this.inner.request(method, url, { ...options, ttl: null });
    const key = CachingTransport.key(method, url, options.params, options.json);
    const running = this.inFlight.get(key);
    if (running !== undefined) return running;
    const work = this.fetchOrServe(key, method, url, options, ttl);
    this.inFlight.set(key, work);
    try {
      return await work;
    } finally {
      this.inFlight.delete(key);
    }
  }

  private async fetchOrServe(
    key: string,
    method: string,
    url: string,
    options: RequestOptions,
    ttl: number,
  ): Promise<HttpResponse> {
    const cached = await this.load(key);
    if (cached !== null && this.clock() - cached.storedAt < ttl) return cached;
    const { validate, ...forward } = options;
    let live: HttpResponse;
    try {
      live = await this.inner.request(method, url, forward);
    } catch (error) {
      if (error instanceof TransportError && cached !== null) return cached.with({ stale: true });
      throw error;
    }
    if ((live.status >= 500 || STALE_ON.has(live.status)) && cached !== null) {
      return cached.with({ stale: true });
    }
    if (live.status === 200) {
      if (validate) {
        try {
          validate(live);
        } catch {
          return cached !== null ? cached.with({ stale: true }) : live;
        }
      }
      await this.store(key, live);
    }
    return live;
  }
}
