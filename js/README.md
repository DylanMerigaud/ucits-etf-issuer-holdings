# ucits-etf-issuer-holdings

Full holdings of a UCITS ETF by ISIN, read from the issuer's own published files, in one JSON
shape: iShares, Vanguard, Xtrackers, Amundi, SPDR and Invesco. Zero runtime dependencies, Node 20
or later, typed. The same library exists for Python and emits the same JSON.

Use it for portfolio look-through, asset allocation or a holdings export when a data vendor is
not an option.

## Install

```sh
npm install ucits-etf-issuer-holdings
```

## Use

```ts
import { HoldingsClient, weightsBy, topHoldings, totalWeight } from "ucits-etf-issuer-holdings";

const client = new HoldingsClient();
const fund = await client.get("IE00B4L5Y983"); // asks each issuer in turn, cached on disk

console.log(fund.fund_name, fund.issuer, fund.as_of, fund.holdings.length);
console.log(totalWeight(fund)); // percent
console.log(weightsBy(fund, "country").slice(0, 3)); // [["US", 71.2], ...]
console.log(topHoldings(fund, 5).map((h) => `${h.name} ${h.weight}`));
```

`client.get(isin, { issuer: "ishares" })` asks one issuer only. When no issuer returns holdings
the call rejects with `FundNotFound`, whose `reasons` say why each one did not. Look-through over
several funds: `lookThrough({ IE00B4L5Y983: 7000, IE00BK5BQT80: 3000 }, funds, "country")`.

Command line: `npx ucits-holdings IE00B4L5Y983 --format table --by country`.

## Offline

The package ships recorded answers of every issuer, so examples and tests run without a network:

```ts
import { HoldingsClient } from "ucits-etf-issuer-holdings";
import { recordedTransport, RECORDED_ISINS } from "ucits-etf-issuer-holdings/testing";

const client = new HoldingsClient({ transport: recordedTransport() });
for (const isin of RECORDED_ISINS) {
  const fund = await client.get(isin);
  console.log(isin, fund.issuer, fund.holdings.length);
}
```

## More

The issuer table (which fund list and endpoint each issuer uses), the comparison with other
libraries, the JSON schema and the Python package are in the main README:
https://github.com/DylanMerigaud/ucits-etf-issuer-holdings#readme

The library fetches one file per fund from each issuer's public product pages and sends an
identifying user agent. You are responsible for the issuers' website terms.

MIT license.
