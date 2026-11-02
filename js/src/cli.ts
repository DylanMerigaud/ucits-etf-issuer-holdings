#!/usr/bin/env node
import { main } from "./cliMain.js";

process.exitCode = await main(process.argv.slice(2));
