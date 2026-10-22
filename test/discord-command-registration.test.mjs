import test from "node:test";
import assert from "node:assert/strict";
import { commands, retired, registerDiscordCommands } from "../scripts/register-discord-commands.mjs";

test("register global commands for server and user installs; retire old ones; no home-server duplicates", async () => {
  const calls = [];
  await registerDiscordCommands({ DISCORD_APPLICATION_ID: "123456789012345678",
    DISCORD_GUILD_ID: "223456789012345678", DISCORD_BOT_TOKEN: "test-only" }, async (url, init) => {
    calls.push({ url, method: init.method, body: init.body && JSON.parse(init.body) });
    if (init.method !== "GET") return Response.json({});
    return Response.json(url.includes("/guilds/") ? [
      { name: "profile", type: 1, id: "523456789012345678" },
      { name: "player", type: 1, id: "623456789012345678" },
      { name: "unrelated", type: 1, id: "723456789012345678" },
    ] : [
      { name: "feedback", type: 1, id: "323456789012345678" },
      { name: "unrelated", type: 1, id: "423456789012345678" },
    ]);
  });
  assert.deepEqual(commands.map(c => c.name), ["profile", "player", "cfn", "me", "vs", "leaderboard", "server-leaderboard", "character", "replay", "link", "alias", "queue", "help",
    "SF Stats profile", "Compare with me", "setup"]);
  assert.deepEqual(retired, ["feedback"]);
  const posts = calls.filter(c => c.method === "POST");
  assert.equal(posts.length, commands.length);
  for (const call of posts) {
    assert.ok(!call.url.includes("/guilds/"));
    const setup = call.body.name === "setup";
    assert.deepEqual(call.body.integration_types, setup ? [0] : [0, 1]);
    assert.deepEqual(call.body.contexts, setup ? [0] : [0, 1, 2]);
    assert.equal(call.body.default_member_permissions, setup ? "32" : undefined, "only setup needs Manage Server");
    if (call.body.type === 2) assert.equal(call.body.description, undefined, "user commands have no description");
    else assert.ok(call.body.description.length <= 100);
    for (const option of call.body.options ?? []) assert.ok(option.description.length <= 100 && /^[a-z_]{1,32}$/.test(option.name));
  }
  const autocomplete = posts.flatMap(c => c.body.options ?? []).filter(o => o.autocomplete).map(o => o.name);
  assert.deepEqual([...new Set(autocomplete)].sort(), ["character", "country", "name", "opponent", "player"]);
  const deleted = calls.filter(c => c.method === "DELETE").map(c => c.url.split("/").at(-1)).sort();
  assert.deepEqual(deleted, ["323456789012345678", "523456789012345678", "623456789012345678"], "home copies and retired commands go; unrelated ones stay");
  assert.ok(calls.every(c => c.method !== "PUT"));
});

test("registration rejects bad configuration and stops on Discord errors", async () => {
  await assert.rejects(registerDiscordCommands({}, () => { throw new Error("unexpected request"); }), /Set DISCORD/);
  await assert.rejects(registerDiscordCommands({ DISCORD_APPLICATION_ID: "123456789012345678",
    DISCORD_GUILD_ID: "223456789012345678", DISCORD_BOT_TOKEN: "test-only" },
    async () => Response.json({}, { status: 403 })), /HTTP 403/);
});

test("registration waits out rate limits instead of failing", async () => {
  const env = { DISCORD_APPLICATION_ID: "123456789012345678", DISCORD_GUILD_ID: "223456789012345678", DISCORD_BOT_TOKEN: "test-only" };
  let limited = 0;
  await registerDiscordCommands(env, async (_url, init) => {
    if (init.method === "POST" && limited++ < 2) return Response.json({ retry_after: 0.01 }, { status: 429 });
    return init.method === "GET" ? Response.json([]) : Response.json({});
  });
  assert.equal(limited > 2, true, "retried after each 429");
  await assert.rejects(registerDiscordCommands(env, async () => Response.json({ retry_after: 0.01 }, { status: 429 })), /kept being rate limited/);
});
