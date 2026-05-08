import { copyFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
copyFileSync(join(root, "index.html"), join(dist, "index.html"));
copyFileSync(join(root, "app.js"), join(dist, "app.js"));
copyFileSync(join(root, "styles.css"), join(dist, "styles.css"));

console.log("frontend built to frontend/dist");
