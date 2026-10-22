import test from "node:test";
import assert from "node:assert/strict";
import { reactionPayload, deliverReaction } from "../scripts/discord-reaction-gateway.mjs";

const config = { applicationId: "1000000000000000792", guildId: "2000000000000000000", channelId: "1000000000000000793" };
const user = { id: "1000000000000000794", bot: false };
const reaction = { message: { id: "1000000000000000795", guildId: config.guildId, channelId: config.channelId }, emoji: { id: null, name: "🔔" } };

test("only human bell reactions in the configured guild and channel are forwarded", () => {
  assert.deepEqual(reactionPayload(reaction, user, false, config), { messageId: reaction.message.id, userId: user.id, subscribed: false });
  for (const modified of [
    { ...reaction, emoji: { id: "1000000000000000796", name: "🔔" } },
    { ...reaction, emoji: { name: "👍" } },
    { ...reaction, message: { ...reaction.message, guildId: "1000000000000000796" } },
    { ...reaction, message: { ...reaction.message, channelId: "1000000000000000796" } },
  ]) assert.equal(reactionPayload(modified, user, true, config), null);
  for (const modified of [{ ...user, bot: true }, { ...user, bot: undefined }, { ...user, id: config.applicationId }]) {
    assert.equal(reactionPayload(reaction, modified, true, config), null);
  }
});

test("transient failures retry boundedly and preserve subscription removal", async () => {
  const calls = [], waits = [];
  const payload = reactionPayload(reaction, user, false, config);
  const ok = await deliverReaction(payload, "test-secret", { sleep: async ms => waits.push(ms), fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return new Response(null, { status: calls.length < 4 ? 503 : 200 });
  } });
  assert.equal(ok, true);
  assert.equal(calls.length, 4);
  assert.deepEqual(waits, [500, 1000, 2000]);
  assert.equal(calls[0].url, "http://127.0.0.1:3010/internal/discord/reactions");
  assert.equal(calls[0].options.headers.Authorization, "Bearer test-secret");
  assert.deepEqual(JSON.parse(calls[3].options.body), payload);
});

test("permanent HTTP failures do not retry and transient failure eventually stops", async () => {
  for (const [status, expected] of [[401, 1], [404, 1], [429, 4], [503, 4]]) {
    let count = 0;
    assert.equal(await deliverReaction({}, "test", { sleep: async () => {}, fetchImpl: async () => {
      count++; return new Response(null, { status });
    } }), false);
    assert.equal(count, expected);
  }
});

test("shutdown aborts delivery without sending another event", async () => {
  const abort = new AbortController(); abort.abort();
  assert.equal(await deliverReaction({}, "test", { signal: abort.signal, fetchImpl: async () => { throw new Error("Must not send"); } }), false);
});
