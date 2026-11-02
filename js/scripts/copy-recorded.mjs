// Copies the recorded issuer answers and the LICENSE from the repository root into js/,
// so the npm tarball ships them. Run by `npm run build`.
import { cpSync, copyFileSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pkg = join(here, "..");
const root = join(pkg, "..");
const recorded = join(root, "src", "ucits_etf_issuer_holdings", "testing", "recorded");

if (!existsSync(recorded)) {
  console.error(`recorded answers not found at ${recorded}`);
  process.exit(1);
}
rmSync(join(pkg, "recorded"), { recursive: true, force: true });
cpSync(recorded, join(pkg, "recorded"), { recursive: true });
if (existsSync(join(root, "LICENSE"))) {
  copyFileSync(join(root, "LICENSE"), join(pkg, "LICENSE"));
}
