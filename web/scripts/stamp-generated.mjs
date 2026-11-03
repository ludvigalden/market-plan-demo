// Prefix a generated file with a do-not-edit header naming its source.
import { readFileSync, writeFileSync } from "node:fs";

const HEADER =
  "// Generated from contracts/openapi.json by openapi-typescript. Do not edit.\n" +
  "// Regenerate: npm run generate (in web/).\n";

for (const file of process.argv.slice(2)) {
  const body = readFileSync(file, "utf8").replace(
    /^\/\/ Generated from[^\n]*\n\/\/ Regenerate[^\n]*\n/,
    "",
  );
  writeFileSync(file, HEADER + body);
}
