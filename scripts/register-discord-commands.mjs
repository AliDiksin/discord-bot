// Run in a trusted shell with protected Discord variables; never pass tokens as arguments.
import { pathToFileURL } from "node:url";

const STRING = 3;
const player = (name, description, required = false) =>
  ({ name, description, type: STRING, required, autocomplete: true, min_length: 1, max_length: 64 });

/**
 * Each command is obvious from its name. Player, character and country options
 * autocomplete; everything else happens through buttons. /player and /cfn open
 * the same card as /profile, because people reach for all three.
 */
const profile = description => ({ description, options: [player("player", "Name or CFN ID. Leave empty for your linked profile")] });
export const commands = [
  { name: "profile", ...profile("A player's rank, form, matchups, rating, habits and replays") },
  { name: "player", ...profile("Same as /profile: a player's card with tabs") },
  { name: "cfn", ...profile("Same as /profile: look up a CFN profile") },
  { name: "me", description: "Your linked SF6 profile in this server" },
  { name: "vs", description: "Head-to-head record between two players",
    options: [player("player", "Player to compare", true), player("opponent", "Second player. Leave empty to compare against yourself")] },
  { name: "leaderboard", description: "Top players by character and country, globally or in this server",
    options: [
      { name: "character", description: "Filter by character", type: STRING, autocomplete: true, max_length: 40 },
      { name: "country", description: "Filter by country", type: STRING, autocomplete: true, max_length: 80 },
      { name: "scope", description: "Everyone, or only members who linked in this server", type: STRING,
        choices: [{ name: "Global", value: "g" }, { name: "This server", value: "s" }] },
    ] },
  { name: "server-leaderboard", description: "This server's own leaderboard: members who linked with /link",
    options: [
      { name: "character", description: "Filter by character", type: STRING, autocomplete: true, max_length: 40 },
      { name: "country", description: "Filter by country", type: STRING, autocomplete: true, max_length: 80 },
    ] },
  { name: "character", description: "Popularity, win rates, best matchups and top players for a character",
    options: [{ name: "name", description: "Character", type: STRING, required: true, autocomplete: true, max_length: 40 }] },
  { name: "replay", description: "Watch, capture or follow an SF6 replay",
    options: [{ name: "id", description: "Replay ID from SF6 (e.g. ABC1DEF23)", type: STRING, required: true, min_length: 6, max_length: 64 }] },
  { name: "link", description: "Link your SF6 profile in this server so commands default to you",
    options: [player("player", "Your name or CFN ID. Leave empty to see or change your link")] },
  { name: "alias", description: "Your own short names for players, usable in any player option",
    options: [
      { name: "set", description: "Give a player a short name, like daigo", type: 1, options: [
        { name: "name", description: "Short name: letters, digits, _ or -", type: STRING, required: true, min_length: 1, max_length: 24 },
        player("player", "Who it should mean", true)] },
      { name: "remove", description: "Remove one of your aliases", type: 1, options: [
        { name: "name", description: "Alias to remove", type: STRING, required: true, autocomplete: true, max_length: 24 }] },
      { name: "list", description: "See your aliases", type: 1 },
    ] },
  { name: "queue", description: "Replays being captured right now" },
  { name: "help", description: "What SF Stats can do" },
  // Right-click a member → Apps.
  { name: "SF Stats profile", type: 2 },
  { name: "Compare with me", type: 2 },
].map(command => ({ type: 1, ...command,
  // Server installs and user installs; works in servers, DMs and group DMs.
  integration_types: [0, 1], contexts: [0, 1, 2] })).concat([
  // Server settings: Manage Server by default, only where the bot is installed.
  { type: 1, name: "setup", description: "Server settings: rank-up announcements and a replay channel",
    default_member_permissions: "32", integration_types: [0], contexts: [0] },
]);

/** Commands from earlier versions, removed on registration. Anything else is left alone. */
export const retired = ["feedback"];

export async function registerDiscordCommands(env = process.env, request = fetch) {
  const { DISCORD_APPLICATION_ID: app, DISCORD_GUILD_ID: guild, DISCORD_BOT_TOKEN: token } = env;
  if (!/^\d{17,20}$/.test(app ?? "") || !/^\d{17,20}$/.test(guild ?? "") || !token) {
    throw new Error("Set DISCORD_APPLICATION_ID, DISCORD_GUILD_ID and DISCORD_BOT_TOKEN first");
  }
  // One POST per command bursts past Discord's bucket; wait out each 429.
  const api = async (url, method, body) => {
    for (let attempt = 0; attempt < 6; attempt++) {
      const response = await request(url, {
        method, headers: { Authorization: `Bot ${token}`, "Content-Type": "application/json" },
        ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(15_000),
      });
      if (response.status === 429) {
        const wait = Number((await response.json().catch(() => ({}))).retry_after) || 2;
        await new Promise(resolve => setTimeout(resolve, Math.min(wait, 60) * 1000));
        continue;
      }
      if (!response.ok) throw new Error(`Discord command registration returned HTTP ${response.status}`);
      return response;
    }
    throw new Error("Discord command registration kept being rate limited");
  };
  const global = `https://discord.com/api/v10/applications/${app}/commands`;
  const home = `https://discord.com/api/v10/applications/${app}/guilds/${guild}/commands`;
  // POST upserts by name, preserving unrelated commands.
  for (const command of commands) await api(global, "POST", command);
  const ours = new Set(commands.map(c => c.name));
  for (const [url, remove] of [
    [global, name => retired.includes(name)],
    // Home-server copies duplicate the global commands in Discord's picker.
    [home, name => retired.includes(name) || ours.has(name)],
  ]) {
    const registered = await (await api(url, "GET")).json();
    for (const command of registered) {
      if (remove(command.name) && /^\d{17,20}$/.test(command.id)) await api(`${url}/${command.id}`, "DELETE");
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await registerDiscordCommands();
  console.log(`Registered ${commands.map(c => `/${c.name}`).join(", ")} globally; retired ${retired.map(n => `/${n}`).join(", ")}.`);
}
