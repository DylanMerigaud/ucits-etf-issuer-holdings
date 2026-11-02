import { parseArgs } from "node:util";
import { HoldingsClient } from "./client.js";
import { HoldingsError, InvalidISIN } from "./errors.js";
import type { Transport } from "./http.js";
import { ISSUER_ORDER } from "./issuers/index.js";
import { WEIGHT_KEYS, weightsBy, type Fund, type WeightKey } from "./models.js";
import { pyFloat, pyG } from "./pyish.js";
import { VERSION } from "./version.js";

const HOLDING_COLUMNS = [
  "name",
  "weight",
  "isin",
  "ticker",
  "country",
  "country_name",
  "sector",
  "currency",
  "asset_class",
  "asset_class_raw",
] as const;

const USAGE = `usage: ucits-holdings [-h] [--issuer {${ISSUER_ORDER.join(",")}}]
                      [--format {json,csv,table}] [--by {${WEIGHT_KEYS.join(",")}}]
                      [--no-cache] [--version]
                      isin
`;

/** Where the command line writes, and the transport it asks (for tests). */
export interface CliIo {
  transport?: Transport;
  stdout?: (text: string) => void;
  stderr?: (text: string) => void;
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "number" ? pyFloat(value) : String(value);
}

function width(text: string): number {
  return [...text].length;
}

function pad(text: string, size: number): string {
  return text + " ".repeat(Math.max(0, size - width(text)));
}

function csvField(text: string): string {
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function renderRows(header: readonly string[], rows: string[][], format: string): string {
  if (format === "csv") {
    return [header, ...rows].map((r) => r.map(csvField).join(",") + "\n").join("");
  }
  const widths = header.map((h, i) => Math.max(width(h), ...rows.map((r) => width(r[i]!))));
  const line = (r: readonly string[]): string =>
    r.map((c, i) => pad(c, widths[i]!)).join("  ").trimEnd();
  return [line(header), ...rows.map(line)].join("\n") + "\n";
}

function asciiJson(value: unknown): string {
  return JSON.stringify(value, null, 2).replace(
    /[\u0080-￿]/g,
    (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}

function render(fund: Fund, format: string, by: WeightKey | undefined): string {
  if (by !== undefined) {
    const grouped = weightsBy(fund, by);
    if (format === "json") {
      return asciiJson(grouped.map(([k, w]) => ({ [by]: k, weight: w }))) + "\n";
    }
    return renderRows([by, "weight"], grouped.map(([k, w]) => [cell(k), pyG(w)]), format);
  }
  if (format === "json") return JSON.stringify(fund, null, 2) + "\n";
  const rows = fund.holdings.map((h) => HOLDING_COLUMNS.map((col) => cell(h[col])));
  const text = renderRows(HOLDING_COLUMNS, rows, format);
  if (format === "table") {
    const title = `${fund.fund_name || fund.isin} (${fund.issuer}, as of ${fund.as_of || "unknown"})`;
    return `${title}\n\n${text}`;
  }
  return text;
}

/**
 * Run the command line `ucits-holdings ISIN [--issuer NAME] [--format json|csv|table] [--by KEY]
 * [--no-cache]` and return the exit code (0 ok, 1 not found, 2 bad input).
 */
export async function main(argv: readonly string[], io: CliIo = {}): Promise<number> {
  const out = io.stdout ?? ((t: string) => void process.stdout.write(t));
  const err = io.stderr ?? ((t: string) => void process.stderr.write(t));
  const fail = (message: string): number => {
    err(`${USAGE}ucits-holdings: error: ${message}\n`);
    return 2;
  };
  let values: Record<string, string | boolean | undefined>;
  let positionals: string[];
  try {
    const parsed = parseArgs({
      args: [...argv],
      allowPositionals: true,
      options: {
        issuer: { type: "string" },
        format: { type: "string", default: "json" },
        by: { type: "string" },
        "no-cache": { type: "boolean" },
        version: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
    });
    values = parsed.values;
    positionals = parsed.positionals;
  } catch (error) {
    return fail(error instanceof Error ? error.message : String(error));
  }
  if (values["help"]) {
    out(USAGE);
    return 0;
  }
  if (values["version"]) {
    out(`ucits-holdings ${VERSION}\n`);
    return 0;
  }
  if (positionals.length !== 1) {
    return fail(positionals.length === 0 ? "the following arguments are required: isin" : `unrecognized arguments: ${positionals.slice(1).join(" ")}`);
  }
  const issuer = values["issuer"] as string | undefined;
  const format = values["format"] as string;
  const by = values["by"] as string | undefined;
  if (issuer !== undefined && !ISSUER_ORDER.includes(issuer)) {
    return fail(`argument --issuer: invalid choice: '${issuer}' (choose from ${ISSUER_ORDER.join(", ")})`);
  }
  if (!["json", "csv", "table"].includes(format)) {
    return fail(`argument --format: invalid choice: '${format}' (choose from json, csv, table)`);
  }
  if (by !== undefined && !(WEIGHT_KEYS as readonly string[]).includes(by)) {
    return fail(`argument --by: invalid choice: '${by}' (choose from ${WEIGHT_KEYS.join(", ")})`);
  }
  const client = new HoldingsClient({
    ...(io.transport !== undefined ? { transport: io.transport } : {}),
    ...(values["no-cache"] ? { cacheDir: null } : {}),
  });
  let fund: Fund;
  try {
    fund = await client.get(positionals[0]!, issuer !== undefined ? { issuer } : {});
  } catch (error) {
    if (error instanceof HoldingsError) {
      err(`error: ${error.message}\n`);
      return error instanceof InvalidISIN ? 2 : 1;
    }
    throw error;
  }
  out(render(fund, format, by as WeightKey | undefined));
  return 0;
}
