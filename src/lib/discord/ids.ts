/**
 * Component IDs: `s2:<view>:<owner>:<arg>…` (≤100 chars). The owner is the user
 * whose card this is; anyone else who clicks gets a private copy instead.
 * Arguments are validated by each view; nothing here is trusted.
 */
const PREFIX = "s2";
const SNOWFLAKE = /^\d{17,20}$/;
const ARG = /^[A-Za-z0-9_.-]{0,40}$/;

export type ComponentId = { view: string; owner: string; args: string[] };

export function encodeId(view: string, owner: string, ...args: (string | number | bigint)[]) {
  const parts = [PREFIX, view, owner, ...args.map(String)];
  if (!/^[a-z0-9-]{1,12}$/.test(view) || !SNOWFLAKE.test(owner) || parts.slice(3).some(a => !ARG.test(a))) {
    throw new Error("Invalid component ID");
  }
  const id = parts.join(":");
  if (id.length > 100) throw new Error("Component ID too long");
  return id;
}

export function decodeId(value: unknown): ComponentId | null {
  if (typeof value !== "string" || value.length > 100) return null;
  const [prefix, view, owner, ...args] = value.split(":");
  if (prefix !== PREFIX || !view || !/^[a-z0-9-]{1,12}$/.test(view) || !SNOWFLAKE.test(owner ?? "") || args.some(a => !ARG.test(a))) return null;
  return { view, owner, args };
}

/** Earlier bot versions; their cards are answered with a polite refresh hint. */
export const isLegacyId = (value: unknown) => typeof value === "string" && /^(sfplayer|sfboard|sfboard-disabled):/.test(value);

export const int = (value: string | undefined, min = 0, max = 2_147_483_647) =>
  value != null && /^\d{1,10}$/.test(value) && +value >= min && +value <= max ? +value : null;
