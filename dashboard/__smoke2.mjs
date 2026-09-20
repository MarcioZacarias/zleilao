import { chromium } from "playwright";
import fs from "node:fs";
const BASE = "http://localhost:5178";
const SUB = JSON.parse(fs.readFileSync("sub.json", "utf8"));
const problems = [];
const log = (...a) => console.log(...a);
function watch(page, tag) {
  page.on("console", (m) => { if (m.type() === "error") problems.push(`[${tag}] ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`[${tag}] pageerror: ${e.message}`));
}
const t = async (page, sel) => { try { return (await page.locator(sel).first().innerText()).replace(/\s+/g, " ").slice(0, 240); } catch { return "(ausente)"; } };
const browser = await chromium.launch();

/* preview do filtro */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage(); watch(page, "preview");
  await page.goto(BASE + "/entrar", { waitUntil: "networkidle" });
  await page.fill("#email", SUB.email); await page.fill("#password", SUB.password);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await page.waitForFunction(() => location.pathname === "/conta", null, { timeout: 15000 });
  await page.goto(BASE + "/conta?aba=filtros", { waitUntil: "networkidle" });
  await page.waitForSelector("button[aria-label='Ver o que este filtro pega hoje']", { timeout: 15000 });
  await page.locator("button[aria-label='Ver o que este filtro pega hoje']").first().click();
  await page.waitForTimeout(2500);
  log("preview:", await t(page, "aside p.mb-4"));
  log("cards na previa:", await page.locator("aside a[href^='/lote/']").count());
  await page.screenshot({ path: "shots/conta-preview.png", fullPage: true });
  await page.keyboard.press("Escape");

  /* editar filtro */
  await page.waitForTimeout(500);
  await page.locator("button[aria-label='Editar filtro']").first().click();
  await page.waitForTimeout(800);
  log("edicao nome:", await page.getByLabel("Nome do alerta").inputValue());
  await page.screenshot({ path: "shots/conta-editar.png", fullPage: true });
  await page.keyboard.press("Escape");
  await ctx.close();
}

/* mobile */
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage(); watch(page, "mobile");
  await page.goto(BASE + "/entrar", { waitUntil: "networkidle" });
  await page.fill("#email", SUB.email); await page.fill("#password", SUB.password);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await page.waitForFunction(() => location.pathname === "/conta", null, { timeout: 15000 });
  for (const [path, name] of [
    ["/conta?aba=alertas", "m-conta-alertas"], ["/conta?aba=filtros", "m-conta-filtros"],
    ["/conta?aba=perfil", "m-conta-perfil"], ["/conta?aba=plano", "m-conta-plano"],
    ["/busca?brand=Fiat", "m-busca"], ["/cadastro", "m-cadastro"], ["/entrar", "m-entrar"],
  ]) {
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1200);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    log(`mobile ${path} overflow-x = ${over}px`);
    if (over > 0) problems.push(`rolagem horizontal em ${path}: ${over}px`);
    await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
  }
  await ctx.close();
}

/* admin */
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage(); watch(page, "admin");
  await page.goto(BASE + "/login", { waitUntil: "networkidle" });
  await page.fill("#email", "admin@zconnect.ia.br"); await page.fill("#password", "admin123");
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await page.waitForFunction(() => location.pathname.startsWith("/admin"), null, { timeout: 15000 });
  await page.waitForTimeout(2500);
  log("bloco assinantes visivel:", await page.getByText("Assinantes e alertas").isVisible());
  await page.screenshot({ path: "shots/admin-dashboard.png", fullPage: true });

  for (const [path, name] of [["/admin/usuarios", "admin-usuarios"], ["/admin/alertas", "admin-alertas"], ["/admin/jobs", "admin-jobs"], ["/admin/configuracoes", "admin-configuracoes"]]) {
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(2200);
    log(`${path} -> h1="${await t(page, "h1")}"`);
    await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
  }

  await page.goto(BASE + "/admin/jobs", { waitUntil: "networkidle" }); await page.waitForTimeout(1500);
  log("jobs:", (await page.locator("div.mb-6.grid .font-semibold").allInnerTexts()).join(" | "));
  await page.goto(BASE + "/admin/configuracoes", { waitUntil: "networkidle" }); await page.waitForTimeout(2000);
  log("#test-email:", await page.locator("#test-email").count(), "#test-whatsapp:", await page.locator("#test-whatsapp").count());
  log("grupos:", (await page.locator("div.grid.gap-6 > div h2").allInnerTexts()).join(" | "));

  await page.goto(BASE + "/admin/usuarios", { waitUntil: "networkidle" }); await page.waitForTimeout(2000);
  log("colunas:", (await page.locator("thead th").allInnerTexts()).join(" | "));
  await page.locator("button[aria-label='Mudar plano']").first().click(); await page.waitForTimeout(700);
  log("modal plano:", await t(page, "div[role=dialog]"));
  await page.screenshot({ path: "shots/admin-plano-modal.png", fullPage: true });
  await page.keyboard.press("Escape"); await page.waitForTimeout(400);
  await page.locator("button[aria-label='Ver filtros do usuário']").first().click(); await page.waitForTimeout(1800);
  log("drawer filtros do usuario:", await t(page, "aside[role=dialog]"));
  await page.screenshot({ path: "shots/admin-filtros-usuario.png", fullPage: true });
  await ctx.close();
}
await browser.close();
console.log("\n===== PROBLEMAS =====");
console.log(problems.length ? problems.join("\n") : "nenhum");
