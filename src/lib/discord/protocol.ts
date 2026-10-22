import { createHmac, createPublicKey, verify } from "node:crypto";

export function verifyDiscordRequest(body: string, signature: string | null, timestamp: string | null,
  publicKey: string, now = Date.now()): boolean {
  if (!/^[a-f\d]{128}$/i.test(signature ?? "") || !/^[a-f\d]{64}$/i.test(publicKey) ||
      !/^\d{10,}$/.test(timestamp ?? "") || Math.abs(now / 1000 - Number(timestamp)) > 300) return false;
  try {
    const key = createPublicKey({ key: Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"),
      Buffer.from(publicKey, "hex")]), format: "der", type: "spki" });
    return verify(null, Buffer.from(timestamp + body), key, Buffer.from(signature!, "hex"));
  } catch { return false; }
}

/** Separate admission namespace: web headers can never opt into the Discord allowance. */
export function discordRequesterHash(userId: string, secret: string): string {
  if (!/^\d{17,20}$/.test(userId)) throw new Error("Invalid Discord user");
  return createHmac("sha256", secret).update(`discord-user:${userId}`).digest("hex");
}

export function notificationPhase(status: string): "finished" | null {
  if (["ready", "failed"].includes(status)) return "finished";
  return null;
}

export function replayUrl(replayId: string): string {
  return `https://sfstats.app/replays/${encodeURIComponent(replayId)}`;
}
