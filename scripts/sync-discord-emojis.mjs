// Uploads the bot's icons as Discord application emojis. Run in a trusted shell
// with protected Discord variables, like register-discord-commands.mjs:
//
//   node scripts/sync-discord-emojis.mjs            upload missing emojis
//   node scripts/sync-discord-emojis.mjs --replace  re-upload all of ours (after redesigning icons)
//
// Emojis: sf_<icon> (src/lib/discord/icons.json), c_<tool> (character icons),
// r_<n> (rank badges). Unrelated application emojis are never touched.
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import sharp from "sharp";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OURS = /^(sf_[a-z_]+|c_[a-z0-9]+|r_\d{1,2})$/;

/** Every emoji the bot can use, as [name, png]. */
export async function emojiImages() {
  const out = [];
  const icons = JSON.parse(await readFile(path.join(root, "src/lib/discord/icons.json"), "utf8"));
  for (const [key, svg] of Object.entries(icons)) {
    out.push([`sf_${key}`, await sharp(Buffer.from(svg), { density: 600 }).resize(128, 128).png().toBuffer()]);
  }
  const characters = path.join(root, "public/profile-assets/v2/characters");
  for (const file of (await readdir(characters)).filter(f => f.endsWith(".png")).sort()) {
    const tool = file.slice(0, -4).replace(/[^a-z0-9]/g, "");
    out.push([`c_${tool}`, await sharp(path.join(characters, file)).resize(128, 128, { fit: "cover", position: "top" }).png().toBuffer()]);
  }
  const ranks = path.join(root, "public/ranks");
  for (const file of (await readdir(ranks)).filter(f => /^rank\d+_s\.png$/.test(f))) {
    out.push([`r_${file.match(/\d+/)[0]}`, await sharp(path.join(ranks, file)).resize(128, 128, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } }).png().toBuffer()]);
  }
  return out.filter(([name]) => OURS.test(name) && name.length <= 32);
}

export async function syncDiscordEmojis(env = process.env, request = fetch, { replace = false } = {}) {
  const { DISCORD_APPLICATION_ID: app, DISCORD_BOT_TOKEN: token } = env;
  if (!/^\d{17,20}$/.test(app ?? "") || !token) throw new Error("Set DISCORD_APPLICATION_ID and DISCORD_BOT_TOKEN first");
  const api = async (url, method, body) => {
    for (let attempt = 0; attempt < 5; attempt++) {
      const response = await request(`https://discord.com/api/v10/applications/${app}/emojis${url}`, {
        method, headers: { Authorization: `Bot ${token}`, "Content-Type": "application/json" },
        ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(20_000),
      });
      if (response.status === 429) {
        const wait = Number((await response.json().catch(() => ({}))).retry_after) || 2;
        await new Promise(resolve => setTimeout(resolve, Math.min(wait, 30) * 1000));
        continue;
      }
      if (!response.ok) throw new Error(`Discord emoji sync returned HTTP ${response.status}`);
      return response.status === 204 ? null : response.json();
    }
    throw new Error("Discord emoji sync kept being rate limited");
  };
  const existing = new Map(((await api("", "GET"))?.items ?? []).map(e => [e.name, e.id]));
  let uploaded = 0, kept = 0;
  for (const [name, png] of await emojiImages()) {
    if (existing.has(name) && !replace) { kept++; continue; }
    if (existing.has(name)) await api(`/${existing.get(name)}`, "DELETE");
    await api("", "POST", { name, image: `data:image/png;base64,${png.toString("base64")}` });
    uploaded++;
  }
  return { uploaded, kept };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = await syncDiscordEmojis(process.env, fetch, { replace: process.argv.includes("--replace") });
  console.log(`Emoji sync: ${result.uploaded} uploaded, ${result.kept} already present.`);
}
