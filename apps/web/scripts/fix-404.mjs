// Catalyst Web Client Hosting serves plain files and does NOT resolve directory
// URLs: /app/missions/ 404s even though /app/missions/index.html exists. That
// breaks every deep link and every shared investigation URL (they only worked
// if you entered at /app/ and navigated client-side).
//
// Catalyst serves 404.html for any miss (see client-package.json "404"), so we
// inject a shim that rewrites a directory-style path to its real exported file.
// A path that already has a file extension is a genuine miss and falls through
// to the normal styled 404 — which also makes a redirect loop impossible, since
// the retried URL ends in .html.
import { readFileSync, writeFileSync } from "node:fs";

const MARKER = "__drishti_deeplink_shim__";
const SHIM = `<script>/*${MARKER}*/(function(){try{var p=location.pathname;
if(/\\.[a-zA-Z0-9]+$/.test(p))return;
var t=p.replace(/\\/+$/,"")+"/index.html";
if(t===p)return;
location.replace(t+location.search+location.hash);}catch(e){}})();</script>`;

const file = "out/404.html";
const html = readFileSync(file, "utf8");
if (html.includes(MARKER)) {
  console.log("404.html: shim already present");
} else if (!html.includes("<head>")) {
  console.error("404.html: no <head> found — deep links will 404");
  process.exit(1);
} else {
  writeFileSync(file, html.replace("<head>", `<head>${SHIM}`));
  console.log("404.html: deep-link redirect shim injected");
}
