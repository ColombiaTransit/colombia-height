#!/usr/bin/env node
// Genuine MapLibre GL JS + Chromium WebGL smoke against one existing real
// coastal Terrain-RGB MBTiles artifact; no new DEM source research/download.
const fs = require("fs");
const { chromium } = require("playwright");
const out = process.env.MAPLIBRE_SMOKE_DIR || "output/maplibre-preview";

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-webgl",
      "--ignore-gpu-blocklist",
    ],
  });
  const page = await browser.newPage({ viewport: { width: 1100, height: 730 }, deviceScaleFactor: 1 });
  const problems = [];
  const pngs = [];
  page.on("pageerror", e => problems.push(String(e.message || e)));
  page.on("response", r => {
    if (r.url().includes("/tiles/") && r.status() === 200) pngs.push(r.url());
  });
  try {
    await page.goto("http://127.0.0.1:8765/", { waitUntil: "load", timeout: 30000 });
    await page.waitForFunction(() => window.__map && window.__map.getTerrain && window.__map.getTerrain(), { timeout: 45000 });
    await page.waitForFunction(() => window.__terrainReady, { timeout: 45000 });
    await page.waitForTimeout(1800);
    await page.screenshot({ path: out + "/cartagena-maplibre-real-terrain.png", fullPage: true });
    const data = await page.evaluate(() => ({
      hasTerrain: !!window.__map.getTerrain(),
      styleLoaded: window.__map.isStyleLoaded(),
      maplibreVersion: maplibregl.version,
      centerTerrainHeightM: window.__map.queryTerrainElevation([-75.511, 10.424]),
      errors: window.__mapErrors,
      sourceReady: window.__terrainReady,
    }));
    data.loadedActualTerrainPNGTiles = pngs.length;
    data.javascriptErrors = problems;
    data.pngExamples = pngs.slice(0, 4);
    fs.writeFileSync(out + "/browser-smoke-result.json", JSON.stringify(data, null, 2) + "\n");
    console.log("MapLibre GL JS actual real coastal tile smoke:", JSON.stringify(data));
    if (!data.hasTerrain || !data.styleLoaded || !data.sourceReady || pngs.length < 2) {
      throw new Error("MapLibre renderer did not fully load genuine Terrain-RGB from local MBTiles");
    }
    if (problems.length || data.errors.length) {
      throw new Error("MapLibre browser must have ZERO DEM/JS/WebGL errors, including missing sea-tile dimension warnings");
    }
    if (data.centerTerrainHeightM === null || !Number.isFinite(data.centerTerrainHeightM)) {
      throw new Error("MapLibre queryTerrainElevation failed for center point");
    }
    console.log("SUCCESS: genuine MapLibre GL terrain loaded, screenshot and data saved");
  } finally {
    await browser.close();
  }
})().catch(e => { console.error("MapLibre 3D smoke failed:", e); process.exitCode = 1; });
