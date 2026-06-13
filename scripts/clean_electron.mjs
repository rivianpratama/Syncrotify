import { rmSync } from "node:fs";

rmSync("dist-electron", { force: true, recursive: true });
