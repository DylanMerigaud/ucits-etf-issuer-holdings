// Dumps every recorded fund as the Python package builds it (Fund.to_dict()) into
// test/fixtures/python-funds.json, without fetched_at. Needs uv; run from anywhere:
//   npm run snapshot
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const out = join(here, "..", "test", "fixtures", "python-funds.json");

export const PYTHON_DUMP = `
import json
from ucits_etf_issuer_holdings import HoldingsClient
from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, recorded_transport
client = HoldingsClient(transport=recorded_transport(), cache_dir=None)
print(json.dumps({isin: client.get(isin).to_dict() for isin in RECORDED_ISINS}))
`;

/** Run the Python package from the repository root and return {isin: fund dict}. */
export function pythonFunds(uv = process.env.UV ?? "uv") {
  const text = execFileSync(uv, ["run", "python", "-c", PYTHON_DUMP], {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  return JSON.parse(text);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const funds = pythonFunds();
  for (const fund of Object.values(funds)) delete fund.fetched_at;
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(funds, null, 2) + "\n");
  console.log(`wrote ${out} (${Object.keys(funds).length} funds)`);
}
