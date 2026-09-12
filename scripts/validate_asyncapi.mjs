import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(new URL("../contracts/tooling/package.json", import.meta.url));
const { Parser } = require("@asyncapi/parser");
const path = new URL("../contracts/asyncapi/beyvra-asyncapi-3.0.yaml", import.meta.url);
const { document, diagnostics } = await new Parser().parse(await readFile(path, "utf8"));
const errors = diagnostics.filter((diagnostic) => diagnostic.severity === 0);
if (!document || errors.length) {
  for (const error of errors) console.error(`ASYNCAPI_ERROR=${error.code}`);
  throw new Error("AsyncAPI contract validation failed");
}
if (document.version() !== "3.0.0") throw new Error("The mission requires AsyncAPI 3.0.0");
console.log(`ASYNCAPI_VALID=${document.channels().all().length}_CHANNELS`);
