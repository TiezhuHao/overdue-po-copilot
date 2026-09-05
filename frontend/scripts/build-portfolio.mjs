import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";

const require = createRequire(import.meta.url);
const next = require.resolve("next/dist/bin/next");
const result = spawnSync(process.execPath, [next, "build"], {
  stdio: "inherit",
  env: { ...process.env, NEXT_PUBLIC_PORTFOLIO_DEMO: "1" },
});

process.exit(result.status ?? 1);
