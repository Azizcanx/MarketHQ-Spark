#!/usr/bin/env node
// One-time admin credential setup for the MarketHQ commerce panel.
// Run on the VPS: node scripts/set-admin-password.mjs
// The password is read with a hidden prompt and never leaves the machine.
import { createInterface } from "node:readline";
import { randomBytes, scrypt } from "node:crypto";
import { promisify } from "node:util";
import { appendFileSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scryptAsync = promisify(scrypt);
const ENV_PATH = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "frontend", ".env");

async function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const derived = (await scryptAsync(password, salt, 64, { N: 16384, r: 8, p: 1 })).toString("hex");
  // Dot-separated: `$` in .env values gets mangled by dotenv-expand in Next's loader.
  return `scrypt.16384.8.1.${salt}.${derived}`;
}

async function main() {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  let user, pw;
  if (process.env.MHQ_ADMIN_USER && process.env.MHQ_ADMIN_PASSWORD) {
    user = process.env.MHQ_ADMIN_USER.trim();
    pw = process.env.MHQ_ADMIN_PASSWORD;
  } else if (process.stdin.isTTY) {
    const ask = (q) => new Promise((r) => rl.question(q, r));
    user = (await ask("Admin kullanıcı adı [admin]: ")).trim() || "admin";
    pw = await ask("Şifre (gizli): ");
  } else {
    const lines = [];
    for await (const line of rl) lines.push(line);
    user = (lines[0] || "admin").trim() || "admin";
    pw = lines[1] || "";
  }
  rl.close();
  if (!pw || pw.length < 8) {
    console.error("Şifre en az 8 karakter olmalı.");
    process.exit(1);
  }
  const hash = await hashPassword(pw);
  if (!existsSync(ENV_PATH)) throw new Error(`.env bulunamadı: ${ENV_PATH}`);
  let env = readFileSync(ENV_PATH, "utf8");
  const set = (key, value) => {
    // Plain values: hash format avoids `$` entirely (dotenv-expand would eat it).
    const line = `${key}=${value.replace(/'/g, "")}`;
    if (new RegExp(`^${key}=`, "m").test(env)) env = env.replace(new RegExp(`^${key}=.*$`, "m"), line);
    else env += `\n${line}\n`;
  };
  set("MARKETHQ_ADMIN_USER", user);
  set("MARKETHQ_ADMIN_PASSWORD_HASH", hash);
  if (!/^MARKETHQ_AUTH_SECRET=/m.test(env)) {
    set("MARKETHQ_AUTH_SECRET", randomBytes(32).toString("hex"));
  }
  writeFileSync(ENV_PATH, env, "utf8");
  console.log(`OK: '${user}' için admin kaydı yazıldı → ${ENV_PATH}`);
  console.log("Uygulamak için: sudo systemctl restart markethq-web");
}

main().catch((e) => { console.error(e.message); process.exit(1); });
