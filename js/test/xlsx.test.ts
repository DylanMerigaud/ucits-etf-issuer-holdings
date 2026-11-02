import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { join } from "node:path";
import { readSheet, XlsxError } from "../dist/xlsx.js";
import { build } from "./xlsxbuild.js";
import { RECORDED_DIR } from "../dist/testing.js";

test("cell types and gaps", () => {
  const sheet =
    '<row r="1"><c r="B1" t="s"><v>0</v></c><c r="D1"><v>1.5</v></c></row>' +
    '<row r="2"><c r="A2" t="inlineStr"><is><t>inline</t></is></c><c r="C2" t="b"><v>1</v></c><c r="E2" t="str"><v>formula text</v></c></row>' +
    '<row r="3"/>';
  for (const deflate of [false, true]) {
    const [name, rows] = readSheet(build(sheet, "<si><t>shared &amp; more</t></si>", deflate));
    assert.equal(name, "Data");
    assert.deepEqual(rows[0], [null, "shared & more", null, 1.5]);
    assert.deepEqual(rows[1], ["inline", null, true, null, "formula text"]);
    assert.deepEqual(rows[2], []);
  }
});

test("rich text shared strings are joined", () => {
  const [, rows] = readSheet(build('<row r="1"><c r="A1" t="s"><v>0</v></c></row>', "<si><r><t>ab</t></r><r><t>cd</t></r></si>"));
  assert.deepEqual(rows[0], ["abcd"]);
});

test("not an xlsx", () => {
  assert.throws(() => readSheet(new TextEncoder().encode("<html>500</html>")), XlsxError);
});

function recorded(path: string): Uint8Array {
  return new Uint8Array(readFileSync(join(RECORDED_DIR, path)));
}

test("xtrackers: namespace prefix and sheet2", () => {
  const [name, rows] = readSheet(recorded("xtrackers/LU0274211480.xlsx"));
  assert.equal(name, "2026-11-02");
  const header = rows.find((r) => r.includes("Name"))!;
  assert.deepEqual(header.slice(1), [
    "Name", "ISIN", "Country", "Currency", "Exchange", "Type of Security",
    "Rating", "Primary Listing", "Industry Classification", "Weighting",
  ]);
  const first = rows[rows.indexOf(header) + 1]!;
  assert.equal(first[0], 1);
  assert.equal(typeof first[10], "number");
});

test("spdr: plain workbook", () => {
  const [name, rows] = readSheet(recorded("spdr/spyw-gy.xlsx"));
  assert.equal(name, "holdings");
  assert.equal(rows[0]![0], "Fund Name:");
  assert.equal(rows[1]![0], "ISIN:");
  assert.deepEqual(rows[4], []);
  assert.equal(rows[5]![0], "ISIN");
});
