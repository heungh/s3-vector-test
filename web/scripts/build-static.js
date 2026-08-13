// Builds a fully static export for CloudFront (demo mode).
// The live API route (app/api) is incompatible with `output: export`, so we
// temporarily move it aside, build, then restore it.
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const apiDir = path.join(root, "app", "api");
const apiBak = path.join(root, ".api-bak");

function move(from, to) {
  if (fs.existsSync(from)) fs.renameSync(from, to);
}

let moved = false;
try {
  if (fs.existsSync(apiDir)) {
    move(apiDir, apiBak);
    moved = true;
    console.log("• moved app/api aside for static export");
  }
  execSync("next build", {
    cwd: root,
    stdio: "inherit",
    env: { ...process.env, STATIC_EXPORT: "1", NEXT_PUBLIC_DEMO_MODE: "1" },
  });
  console.log("\n✅ static export ready in web/out (demo mode)");
} finally {
  if (moved) {
    move(apiBak, apiDir);
    console.log("• restored app/api");
  }
}
