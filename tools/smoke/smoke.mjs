// Headless-Chromium smoke of the primary journey; any failed check exits non-zero.
//   node tools/smoke/smoke.mjs <base-url> <expected-model-deployment> [screenshot-dir]

import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const [base, expectedDeployment, shots = "smoke-output"] =
  process.argv.slice(2);
if (!base || !expectedDeployment) {
  console.error(
    "usage: smoke.mjs <base-url> <expected-model-deployment> [screenshot-dir]",
  );
  process.exit(2);
}
mkdirSync(shots, { recursive: true });

const started = Date.now();
const log = (...a) =>
  console.log(`[${((Date.now() - started) / 1000).toFixed(1)}s]`, ...a);
const fail = (msg) => {
  throw new Error(msg);
};

const browser = await chromium.launch();
const page = await browser.newPage();
page.setDefaultTimeout(90_000);
const serverErrors = [];
page.on("response", (r) => {
  if (r.status() >= 500) serverErrors.push(`${r.status()} ${r.url()}`);
});

let campaignId = "";
try {
  // A scaled-to-zero app answers the first request after a cold start.
  await page.goto(`${base}/`, { timeout: 180_000 });
  await page.getByRole("heading", { level: 1, name: "Campaigns" }).waitFor();

  const styles = await page.evaluate(() => ({
    font: getComputedStyle(document.body).fontFamily,
    accent: getComputedStyle(document.documentElement)
      .getPropertyValue("--accent")
      .trim(),
    button: getComputedStyle(document.querySelector("button")).backgroundColor,
  }));
  log("computed styles:", styles);
  if (
    styles.font.includes("Times") ||
    styles.accent !== "#1f5f8b" ||
    styles.button !== "rgb(31, 95, 139)"
  )
    fail("stylesheet not applied");

  const name = `Spring Essentials (smoke ${new Date().toISOString().slice(0, 19)})`;
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create campaign" }).click();
  await page.getByRole("heading", { level: 1, name }).waitFor();
  campaignId = new URL(page.url()).pathname.split("/").pop();
  log("created:", page.url());

  for (const code of ["SE", "DE", "FR", "US", "JP"])
    await page.getByLabel(new RegExp(`\\(${code}\\)`)).check();
  await page.getByRole("button", { name: "Save markets" }).click();
  await page.getByText("Markets set: DE, FR, JP, SE, US.").waitFor();
  const seFlags = await page
    .getByRole("list", { name: "Holiday flags for Sweden" })
    .innerText();
  log("SE flags:", seFlags.replaceAll("\n", " | "));
  if (!/Launch on holiday\s*1 May 2026/.test(seFlags))
    fail("live holidays did not flag the SE launch on 1 May");

  await page.getByRole("button", { name: "Draft local adaptations" }).click();
  await page.getByText(/suggestion\(s\) drafted/).waitFor();
  log("notice:", await page.locator(".notice").innerText());
  await page.locator(".suggestions .meta").first().waitFor();
  const metas = await page.locator(".suggestions .meta").allInnerTexts();
  log("suggestion provenance:", [...new Set(metas)]);
  if (metas.length === 0) fail("no suggestions rendered");
  if (!metas.every((m) => m.startsWith(`${expectedDeployment} ·`)))
    fail(
      `suggestions not attributed to ${expectedDeployment}: ${[...new Set(metas)]}`,
    );

  const accept = page
    .getByRole("button", { name: /^Accept: SE Move launch to / })
    .first();
  const label = await accept.getAttribute("aria-label");
  const newStart = label.replace("Accept: SE Move launch to ", "");
  await accept.click();
  await page.getByText(`Accepted: SE – Move launch to ${newStart}.`).waitFor();
  log("accepted:", label);
  await page.screenshot({ path: `${shots}/before-reload.png`, fullPage: true });

  await page.reload();
  await page.getByRole("heading", { level: 1, name }).waitFor();
  const seDates = await page.getByTestId("dates-SE").innerText();
  log("SE dates after reload:", seDates);
  if (!seDates.startsWith(`${newStart} –`))
    fail("accepted launch shift did not persist");
  const audit = await page
    .getByRole("table")
    .last()
    .locator("tbody tr")
    .allInnerTexts();
  log(
    "audit after reload:",
    audit.map((r) => r.replaceAll("\t", " ")),
  );
  if (
    !audit.some(
      (r) =>
        r.includes("SE") &&
        r.includes("accepted") &&
        r.includes(`${expectedDeployment} /`),
    )
  )
    fail(
      "audit does not show the accepted SE decision with its model deployment",
    );
  await page.screenshot({ path: `${shots}/after-reload.png`, fullPage: true });

  if (serverErrors.length) fail(`5xx responses: ${serverErrors.join(", ")}`);
  log(`SMOKE OK in ${((Date.now() - started) / 1000).toFixed(1)}s`);
} finally {
  if (campaignId) {
    const r = await page.request.delete(`${base}/api/campaigns/${campaignId}`);
    log("cleanup delete:", r.status());
  }
  await browser.close();
}
