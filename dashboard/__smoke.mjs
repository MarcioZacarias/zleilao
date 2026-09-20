import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://localhost:5178";
const SUB = JSON.parse(fs.readFileSync("sub.json", "utf8")); // {email, password}
const ADMIN = { email: "admin@zconnect.ia.br", password: "admin123" };

const problems = [];
const log = (...a) => console.log(...a);

function watch(page, tag) {
  page.on("console", (m) => {
    if (m.type() === "error") {
      const t = m.text();
      if (t.includes("favicon") || t.includes("Failed to load resource")) return;
      problems.push(`[${tag}] console: ${t}`);
    }
  });
  page.on("pageerror", (e) => problems.push(`[${tag}] pageerror: ${e.message}`));
}

async function shot(page, name) {
  await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
}

async function textOf(page, sel) {
  try {
    return (await page.locator(sel).first().innerText()).replace(/\s+/g, " ").slice(0, 200);
  } catch {
    return "(ausente)";
  }
}

const browser = await chromium.launch();

/* ── 1. Telas públicas de conta ─────────────────────────────── */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  watch(page, "publico");

  for (const [path, name] of [
    ["/cadastro", "cadastro"],
    ["/entrar", "entrar"],
    ["/esqueci-senha", "esqueci-senha"],
    ["/redefinir-senha?token=abc", "redefinir-senha"],
    ["/verificar-email?token=tokeninvalido", "verificar-email-erro"],
  ]) {
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(400);
    log(`${path} -> h1="${await textOf(page, "h1")}"`);
    await shot(page, name);
  }

  // verificar-email sem token
  await page.goto(BASE + "/verificar-email", { waitUntil: "networkidle" });
  log(`/verificar-email (sem token) -> "${await textOf(page, "p.mt-3")}"`);

  await ctx.close();
}

/* ── 2. Portal deslogado: header mostra "Entrar" ─────────────── */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  watch(page, "portal-deslogado");
  await page.goto(BASE + "/busca?brand=Fiat&state=CE", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  log("header deslogado tem 'Entrar':", await page.locator("header a[href='/entrar']").count());
  log("header deslogado tem 'Admin' fixo:", await page.locator("header a[href='/admin']").count());
  const btn = page.getByRole("button", { name: /Criar alerta desta busca/i });
  log("botao criar alerta visivel:", await btn.isVisible());
  await shot(page, "busca-deslogado");

  // Sem sessao: manda para /entrar preservando a intencao
  await btn.click();
  await page.waitForFunction(() => location.pathname === "/entrar" && location.search.includes("next="), null, { timeout: 15000 });
  log("redirect ->", decodeURIComponent(page.url()));
  await ctx.close();
}

/* ── 3. Assinante: login, criar alerta a partir da busca ─────── */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  watch(page, "assinante");

  await page.goto(BASE + "/busca?brand=Fiat&price_max=60000&state=CE", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: /Criar alerta desta busca/i }).click();
  await page.waitForFunction(() => location.pathname === "/entrar", null, { timeout: 15000 });

  await page.fill("#email", SUB.email);
  await page.fill("#password", SUB.password);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await page.waitForFunction(() => location.pathname === "/busca", null, { timeout: 15000 });
  await page.waitForTimeout(1200);

  const drawerTitle = await textOf(page, "aside[role=dialog]:visible h2");
  log("apos login, drawer aberto:", drawerTitle);
  log("nome sugerido:", await page.getByLabel("Nome do alerta").inputValue().catch(() => "(sem campo)"));
  log("chips do criterio:", await page.locator("aside[role=dialog]:visible span.rounded-full:visible").allInnerTexts());
  log("URL limpa de criar_alerta:", !page.url().includes("criar_alerta"));
  await shot(page, "criar-alerta-drawer");

  // Acima do limite do plano free -> 403 com o texto pronto da API
  await page.locator("aside button", { hasText: /^Criar alerta$/ }).click();
  await page.waitForTimeout(2500);
  log("mensagem de limite (403):", await textOf(page, "div[role=alert]:visible"));
  await shot(page, "criar-alerta-403");
  await page.keyboard.press("Escape");

  // Header logado
  await page.waitForTimeout(300);
  log("header logado mostra nome:", await textOf(page, "header nav button[aria-haspopup=menu]"));
  await page.locator("header nav button[aria-haspopup=menu]").click();
  await page.waitForTimeout(200);
  log("menu:", await page.locator("div[role=menu]").allInnerTexts());
  await shot(page, "header-menu-assinante");

  // /conta
  await page.locator("div[role=menu] a[href='/conta']").click();
  await page.waitForFunction(() => location.pathname === "/conta", null, { timeout: 15000 });
  await page.waitForTimeout(1200);
  log("conta h1:", await textOf(page, "h1"));
  log("abas:", await page.locator("nav[aria-label='Seções da conta'] button").allInnerTexts());
  await shot(page, "conta-alertas");

  for (const aba of ["filtros", "perfil", "plano"]) {
    await page.goto(`${BASE}/conta?aba=${aba}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(900);
    log(`aba ${aba} -> "${await textOf(page, "div.mt-6 h2")}"`);
    await shot(page, `conta-${aba}`);
  }

  // Prévia do filtro
  await page.goto(`${BASE}/conta?aba=filtros`, { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  await page.getByRole("button", { name: /Ver o que este filtro pega hoje/i }).first().click();
  await page.waitForTimeout(1500);
  log("preview:", await textOf(page, "aside[role=dialog] p.mb-4:visible"));
  await shot(page, "conta-preview");

  await ctx.close();
}

/* ── 4. Mobile: sem rolagem horizontal ───────────────────────── */
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  watch(page, "mobile");
  await page.goto(BASE + "/entrar", { waitUntil: "networkidle" });
  await page.fill("#email", SUB.email);
  await page.fill("#password", SUB.password);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await page.waitForFunction(() => location.pathname === "/conta", null, { timeout: 15000 });

  for (const [path, name] of [
    ["/conta?aba=alertas", "m-conta-alertas"],
    ["/conta?aba=filtros", "m-conta-filtros"],
    ["/conta?aba=perfil", "m-conta-perfil"],
    ["/conta?aba=plano", "m-conta-plano"],
    ["/busca?brand=Fiat", "m-busca"],
    ["/cadastro", "m-cadastro"],
  ]) {
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(900);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    log(`mobile ${path} overflow-x = ${over}px`);
    if (over > 0) problems.push(`rolagem horizontal em ${path}: ${over}px`);
    await shot(page, name);
  }
  await ctx.close();
}

/* ── 5. Admin ────────────────────────────────────────────────── */
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  watch(page, "admin");
  await page.goto(BASE + "/login", { waitUntil: "networkidle" });
  await page.fill("#email", ADMIN.email);
  await page.fill("#password", ADMIN.password);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await page.waitForFunction(() => location.pathname.startsWith("/admin"), null, { timeout: 15000 });
  await page.waitForTimeout(2000);
  log("dashboard tem bloco de assinantes:", await page.getByText("Assinantes e alertas").isVisible());
  log("bloco:", await textOf(page, "div.grid.grid-cols-2.gap-3"));
  await shot(page, "admin-dashboard");

  for (const [path, name] of [
    ["/admin/usuarios", "admin-usuarios"],
    ["/admin/alertas", "admin-alertas"],
    ["/admin/jobs", "admin-jobs"],
    ["/admin/configuracoes", "admin-configuracoes"],
  ]) {
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1800);
    log(`${path} -> h1="${await textOf(page, "h1")}"`);
    await shot(page, name);
  }

  // Jobs novos
  await page.goto(BASE + "/admin/jobs", { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  log("jobs listados:", await page.locator("div.mb-6.grid .font-semibold").allInnerTexts());

  // Testes de envio nas Configurações
  await page.goto(BASE + "/admin/configuracoes", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  log("tem #test-email:", await page.locator("#test-email").count());
  log("tem #test-whatsapp:", await page.locator("#test-whatsapp").count());
  log("grupos:", await page.locator("div.grid.gap-6 h2").allInnerTexts());

  // Modal de plano
  await page.goto(BASE + "/admin/usuarios", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  log("colunas:", await page.locator("thead th").allInnerTexts());
  await page.locator("button[aria-label='Mudar plano']").first().click();
  await page.waitForTimeout(500);
  log("modal plano:", await textOf(page, "div[role=dialog]:visible"));
  await shot(page, "admin-plano-modal");
  await page.keyboard.press("Escape");

  // Painel de filtros do usuário
  await page.locator("button[aria-label='Ver filtros do usuário']").first().click();
  await page.waitForTimeout(1200);
  log("drawer filtros:", await textOf(page, "aside[role=dialog]:visible"));
  await shot(page, "admin-filtros-usuario");
  await ctx.close();
}

await browser.close();

console.log("\n===== PROBLEMAS =====");
console.log(problems.length ? problems.join("\n") : "nenhum");
