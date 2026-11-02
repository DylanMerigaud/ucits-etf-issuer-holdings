import { posix } from "node:path";
import { attr, parseXml, type XmlNode } from "./xml.js";
import { ZipReader } from "./zip.js";

/** One spreadsheet cell: text, number, boolean, or null for an empty cell. */
export type Cell = string | number | boolean | null;

/** Raised when bytes are not a readable workbook. */
export class XlsxError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "XlsxError";
  }
}

const REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

function children(node: XmlNode, name: string): XmlNode[] {
  return node.children.filter((c) => c.name === name);
}

function textOf(node: XmlNode): string {
  let out = node.name === "t" ? node.text : "";
  for (const child of node.children) out += textOf(child);
  return out;
}

function columnIndex(ref: string): number {
  const match = /^([A-Z]+)/.exec(ref);
  if (match === null) throw new XlsxError(`bad cell reference '${ref}'`);
  let index = 0;
  for (const ch of match[1]!) index = index * 26 + (ch.charCodeAt(0) - 64);
  return index - 1;
}

function sharedStrings(zip: ZipReader): string[] {
  if (!zip.has("xl/sharedStrings.xml")) return [];
  const root = parseXml(zip.read("xl/sharedStrings.xml").toString("utf8"));
  return children(root, "si").map(textOf);
}

function firstSheet(zip: ZipReader): [string, string] {
  const workbook = parseXml(zip.read("xl/workbook.xml").toString("utf8"));
  const sheets = children(workbook, "sheets")[0];
  const first = sheets === undefined ? undefined : children(sheets, "sheet")[0];
  if (first === undefined) throw new XlsxError("no sheet in the workbook");
  const relId = attr(first, "id", REL_NS);
  const rels = parseXml(zip.read("xl/_rels/workbook.xml.rels").toString("utf8"));
  for (const rel of rels.children) {
    if (attr(rel, "Id") === relId) {
      const target = attr(rel, "Target") ?? "";
      const path = target.startsWith("/") ? target.slice(1) : posix.join("xl", target);
      return [attr(first, "name") ?? "", posix.normalize(path)];
    }
  }
  throw new XlsxError(`no relationship '${relId}' for the first sheet`);
}

function cellValue(cell: XmlNode, shared: string[]): Cell {
  const kind = attr(cell, "t");
  if (kind === "inlineStr") return textOf(cell);
  const v = children(cell, "v")[0];
  const raw = v === undefined || v.text === "" ? null : v.text;
  if (raw === null) return null;
  if (kind === "s") {
    const text = shared[parseInt(raw, 10)];
    if (text === undefined) throw new XlsxError(`shared string ${raw} out of range`);
    return text;
  }
  if (kind === "b") return raw.trim() === "1";
  if (kind === "str" || kind === "e") return raw;
  return NUMBER.test(raw.trim()) ? Number(raw.trim()) : raw;
}

/**
 * Return the name and the rows of the first sheet of an xlsx file.
 *
 * Missing cells inside a row, including leading ones, are null.
 *
 * @throws {XlsxError} when the bytes are not a readable workbook.
 */
export function readSheet(data: Uint8Array): [name: string, rows: Cell[][]] {
  let name: string;
  let sheet: XmlNode;
  let shared: string[];
  try {
    const zip = new ZipReader(data);
    let path: string;
    [name, path] = firstSheet(zip);
    shared = sharedStrings(zip);
    sheet = parseXml(zip.read(path).toString("utf8"));
  } catch (error) {
    if (error instanceof XlsxError) throw error;
    throw new XlsxError(`not a readable xlsx: ${error instanceof Error ? error.message : error}`);
  }
  const rows: Cell[][] = [];
  for (const sheetData of children(sheet, "sheetData")) {
    for (const row of children(sheetData, "row")) {
      const values: Cell[] = [];
      children(row, "c").forEach((cell, position) => {
        const ref = attr(cell, "r");
        const column = ref ? columnIndex(ref) : position;
        while (values.length < column) values.push(null);
        values.push(cellValue(cell, shared));
      });
      rows.push(values);
    }
  }
  return [name, rows];
}
