export function discordInviteUrl(): string | null {
  const value = process.env.SFSTATS_DISCORD_INVITE_URL?.trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password &&
      ((url.hostname === "discord.gg" && /^\/[\w-]+$/.test(url.pathname)) ||
       (url.hostname === "discord.com" && /^\/invite\/[\w-]+$/.test(url.pathname))) ? url.href : null;
  } catch { return null; }
}

export function discordEnabled(): boolean {
  return process.env.SFSTATS_DISCORD_ENABLED === "true" &&
    Boolean(process.env.DISCORD_BOT_TOKEN?.trim()) &&
    /^[a-f\d]{64}$/i.test(process.env.DISCORD_PUBLIC_KEY ?? "") &&
    /^\d{17,20}$/.test(process.env.DISCORD_APPLICATION_ID ?? "") &&
    /^\d{17,20}$/.test(process.env.DISCORD_GUILD_ID ?? "");
}

export function discordPublicConfig() {
  // Publishing the community is a separate decision from configuring the bot.
  const inviteUrl = process.env.SFSTATS_DISCORD_INVITES_ENABLED === "true" ? discordInviteUrl() : null;
  return { inviteUrl, enabled: discordEnabled() && !!inviteUrl };
}
