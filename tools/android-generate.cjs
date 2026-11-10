/* Regenerates the Android projects in android/mail and android/admin from their twa-manifest.json
   with Bubblewrap's generator (npm i @bubblewrap/core). ICON_BASE swaps the icon host while
   generating, e.g. ICON_BASE=http://127.0.0.1:8766 with the web folder served locally. */
const path = require("path"), fs = require("fs");
const {TwaManifest, TwaGenerator, ConsoleLog} = require(process.env.BUBBLEWRAP_CORE || "@bubblewrap/core");
(async () => {
  for (const app of (process.argv[2] ? [process.argv[2]] : ["mail", "admin"])) {
    const dir = path.join(__dirname, "..", "android", app), json = JSON.parse(fs.readFileSync(path.join(dir, "twa-manifest.json"), "utf8"));
    const local = JSON.parse(JSON.stringify(json));
    if (process.env.ICON_BASE) {
      const swap = u => u && u.replace(/^https:\/\/[^/]+/, process.env.ICON_BASE);
      for (const k of ["iconUrl", "maskableIconUrl", "monochromeIconUrl", "webManifestUrl"]) local[k] = swap(local[k]);
      local.shortcuts = (local.shortcuts || []).map(s => ({...s, chosenIconUrl: swap(s.chosenIconUrl)}));
    }
    await new TwaGenerator().createTwaProject(dir, new TwaManifest(local), new ConsoleLog(app));
    fs.writeFileSync(path.join(dir, "twa-manifest.json"), JSON.stringify(json, null, 2) + "\n");  // keep the real URLs
    console.log("generated", app);
  }
})().catch(e => { console.error(e); process.exit(1); });
