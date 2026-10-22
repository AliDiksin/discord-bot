import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const endpoint = "http://127.0.0.1:3010/internal/discord/reactions";
const snowflake = /^\d{17,20}$/;

export function reactionPayload(reaction, user, subscribed, config) {
  const message = reaction.message;
  if (user.bot !== false || user.id === config.applicationId ||
      !snowflake.test(user.id ?? "") || !snowflake.test(message?.id ?? "") ||
      (message.guildId ?? message.channel?.guildId) !== config.guildId ||
      message.channelId !== config.channelId || reaction.emoji?.id ||
      reaction.emoji?.name !== "🔔") return null;
  return { messageId: message.id, userId: user.id, subscribed };
}

export async function deliverReaction(payload, secret, { fetchImpl = fetch, sleep = delay, signal } = {}) {
  for (let attempt = 0; attempt < 4; attempt++) {
    if (signal?.aborted) return false;
    try {
      const response = await fetchImpl(endpoint, {
        method: "POST", headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
      });
      await response.body?.cancel();
      if (response.ok) return true;
      if (response.status !== 429 && response.status < 500) return false;
    } catch { if (signal?.aborted) return false; }
    if (attempt < 3) {
      try { await sleep(500 * 2 ** attempt, undefined, { signal }); }
      catch { return false; }
    }
  }
  return false;
}

async function main() {
  const { Client, Events, GatewayIntentBits, Partials } = await import("discord.js");
  const config = { applicationId: process.env.DISCORD_APPLICATION_ID, guildId: process.env.DISCORD_GUILD_ID,
    channelId: process.env.DISCORD_QUEUE_CHANNEL_ID };
  const secret = process.env.SFSTATS_INTERNAL_SECRET?.trim();
  if (process.env.SFSTATS_DISCORD_ENABLED !== "true" || !Object.values(config).every(v => snowflake.test(v ?? "")) ||
      !process.env.DISCORD_BOT_TOKEN || Buffer.byteLength(secret ?? "") < 32) {
    throw new Error("Gateway configuration incomplete");
  }
  const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessageReactions],
    partials: [Partials.Message, Partials.Reaction, Partials.User, Partials.Channel] });
  const shutdown = new AbortController();
  let chain = Promise.resolve(), pending = 0;
  // Serialize add/remove delivery so a slow add cannot overwrite a later removal.
  const enqueue = (reaction, user, subscribed) => {
    if (shutdown.signal.aborted || pending >= 1000) return;
    const message = reaction.message;
    if (message.channelId !== config.channelId ||
        (message.guildId ?? message.channel?.guildId) !== config.guildId ||
        reaction.emoji?.id || reaction.emoji?.name !== "🔔" || user.bot || user.id === config.applicationId) return;
    pending++;
    chain = chain.then(async () => {
      if (shutdown.signal.aborted) return;
      // Uncached reaction removals can contain partial users. Never fetch the
      // removed reaction itself: its final removal may make that resource vanish.
      const resolvedUser = user.partial ? await user.fetch() : user;
      const payload = reactionPayload(reaction, resolvedUser, subscribed, config);
      if (payload && !await deliverReaction(payload, secret, { signal: shutdown.signal })) {
        console.warn("Reaction delivery deferred to backend reconciliation");
      }
    }).catch(() => console.warn("Reaction event deferred to backend reconciliation"))
      .finally(() => { pending--; });
  };
  client.on(Events.MessageReactionAdd, (reaction, user) => enqueue(reaction, user, true));
  client.on(Events.MessageReactionRemove, (reaction, user) => enqueue(reaction, user, false));
  client.once(Events.ClientReady, () => {
    if (client.user.id !== config.applicationId) { console.error("Gateway application mismatch"); stop(1); return; }
    console.log("Discord reaction gateway ready");
  });
  // Fixed messages only: discord.js errors can contain request paths or tokens.
  client.on(Events.Error, () => console.warn("Discord gateway connection error"));
  client.on(Events.ShardError, () => console.warn("Discord gateway shard error"));
  client.on(Events.ShardReconnecting, () => console.log("Discord gateway reconnecting"));
  client.on(Events.ShardResume, () => console.log("Discord gateway resumed"));
  function stop(code = 0) {
    if (shutdown.signal.aborted) return;
    shutdown.abort();
    client.destroy();
    const forced = setTimeout(() => process.exit(code), 8000);
    chain.finally(() => { clearTimeout(forced); process.exit(code); });
  }
  process.once("SIGTERM", () => stop());
  process.once("SIGINT", () => stop());
  await client.login(process.env.DISCORD_BOT_TOKEN);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error("Discord reaction gateway failed to start"); process.exit(1); });
}
