import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { HttpResponse, type RequestOptions, type Transport } from "./http.js";
import { isObject } from "./pyish.js";

/** The directory of the recorded issuer answers shipped in the package. */
export const RECORDED_DIR = fileURLToPath(new URL("../recorded/", import.meta.url));

/** The ISINs the recorded transport can answer. */
export const RECORDED_ISINS: readonly string[] = [
  "IE00B4L5Y983",
  "IE00B3F81409",
  "IE00BK5BQT80",
  "LU0274211480",
  "IE000BI8OT95",
  "LU1681043599",
  "IE00B5M1WJ87",
  "IE000716YHJ7",
];

interface Entry {
  method: string;
  url: string;
  params: Record<string, unknown> | null;
  match_json: unknown;
  status: number;
  content_type: string;
  file: string;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a)) {
    return Array.isArray(b) && a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  }
  if (isObject(a)) {
    if (!isObject(b)) return false;
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every((k) => k in b && deepEqual(a[k], b[k]));
  }
  return false;
}

/** True when `expected` is contained in `actual`: objects recursively, everything else equal. */
function isSubset(expected: unknown, actual: unknown): boolean {
  if (isObject(expected)) {
    return (
      isObject(actual) &&
      Object.entries(expected).every(([k, v]) => k in actual && isSubset(v, actual[k]))
    );
  }
  return deepEqual(expected, actual);
}

function stringify(params: Record<string, unknown> | null | undefined): Record<string, string> {
  return Object.fromEntries(Object.entries(params ?? {}).map(([k, v]) => [k, String(v)]));
}

/** A {@link Transport} that answers from the recorded files and never touches the network. */
export class RecordedTransport implements Transport {
  /** Every (method, url) asked so far, in order. */
  readonly requests: Array<[method: string, url: string]> = [];
  private readonly dir: string;
  private readonly entries: Entry[];

  /** @param directory folder holding `index.json`; default: the files shipped in the package */
  constructor(directory: string = RECORDED_DIR) {
    this.dir = directory;
    const index = JSON.parse(readFileSync(join(directory, "index.json"), "utf8")) as {
      entries: Entry[];
    };
    this.entries = index.entries;
  }

  private matches(entry: Entry, method: string, url: string, options: RequestOptions): boolean {
    if (entry.method !== method.toUpperCase() || entry.url !== url) return false;
    if (entry.params !== null) {
      if (!deepEqual(sortKeys(stringify(entry.params)), sortKeys(stringify(options.params)))) {
        return false;
      }
    }
    return entry.match_json === null || isSubset(entry.match_json, options.json ?? null);
  }

  /** Return the first recorded answer matching the request, or 404 `not recorded`. */
  async request(method: string, url: string, options: RequestOptions = {}): Promise<HttpResponse> {
    this.requests.push([method.toUpperCase(), url]);
    for (const entry of this.entries) {
      if (this.matches(entry, method, url, options)) {
        const content = new Uint8Array(await readFile(join(this.dir, entry.file)));
        return new HttpResponse(entry.status, content, entry.content_type, url);
      }
    }
    return new HttpResponse(404, new TextEncoder().encode("not recorded"), "text/plain", url);
  }
}

function sortKeys(obj: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(obj).sort(([a], [b]) => (a < b ? -1 : 1)));
}

/** A fresh {@link RecordedTransport} over the files shipped in the package. */
export function recordedTransport(): RecordedTransport {
  return new RecordedTransport();
}
