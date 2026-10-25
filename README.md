# SF Stats Discord bot

The home of the **SF Stats** Discord bot. It has two parts:

| Folder | What it is | Who runs it |
| --- | --- | --- |
| [`bot/`](bot/) | **The bot.** Bub (FrameBub), the frame-data bot for SF6, SFV, USF4, GGST, 2XKO, BBCF, GGACR, COTW, Third Strike, MK1 and AVTL, with its slash commands, `/bub` menus, buttons, images and quiz. It also carries SF Stats: `/cfn`, `/profile`, `/link`, leaderboards and their buttons are forwarded to sfstats.app, and `@SF Stats …` questions are routed between SF Stats and Bub by the site's Decisions check. | The FrameBub application, hosted by Bub's maintainer |
| everything else | The original SF Stats app's open parts: command definitions, the replay-queue 🔔 reaction gateway, emoji sync and the interaction protocol. | The original SF Stats application, alongside sfstats.app |

**Running the bot:** see [`bot/README.md`](bot/README.md). In short, install
`bot/requirements.txt`, copy [`bot/.env.example`](bot/.env.example)
to `bot/.env`, fill it in, then run `python bot.py` from `bot/`. Without the
`SFSTATS_*` settings it runs as plain Bub.

Bub's LLM chatbot (voice, memory, reminders and Streetfighterdle) is becoming its
own bot and is not part of `bot/`.

The rest of this page describes the original SF Stats app's parts.

## SF Stats app parts

The slash command definitions and registration, the replay-queue 🔔 reaction
gateway, the application emoji sync, and the interaction protocol (request
signature verification and component ID format). Install the bot or try it at
<https://sfstats.app/discord>.

> This is not the whole SF Stats backend. Slash commands are **signed HTTP interactions**
> handled inside the sfstats.app backend, which reads the site's database
> directly. Those handlers (the command router and the profile, leaderboard,
> replay, vs, character, alias and setup views) are part of the private web
> application and are not in this repository. What is here is everything that
> runs as its own process or defines the public contract.

## How it fits together

```
Discord ──signed POST──▶ sfstats.app /api/discord/interactions ──▶ command router (private)
Discord ──gateway (this repo)──▶ 🔔 add/remove ──▶ backend reaction endpoint (private)
```

| Piece | Where | What it does |
| --- | --- | --- |
| Command definitions | `scripts/register-discord-commands.mjs` | Every slash and context-menu command, with options and autocomplete flags. Running it upserts them globally and removes retired ones. |
| Reaction gateway | `scripts/discord-reaction-gateway.mjs` | A small discord.js process. Forwards human 🔔 additions and removals from one configured channel to the backend over loopback HTTP. |
| Emoji sync | `scripts/sync-discord-emojis.mjs` | Uploads the bot's icons as application emojis so cards render with custom glyphs. |
| Protocol | `src/lib/discord/protocol.ts`, `ids.ts`, `config.ts` | Ed25519 verification of Discord's request signature, the `s2:<view>:<owner>:<args>` component ID scheme, and the enable/invite configuration checks. |
| Icons | `src/lib/discord/icons.json` | The bot's own SVG icon set. |

Files keep the paths they have in the production tree so they can be copied over
one-to-one.

## Commands

Every player, character and country option autocompletes from saved data, so
nobody needs a CFN ID. Results are public; errors and notices are private. A card
is owned by whoever opened it: the owner's clicks edit it in place, anyone else
gets a private copy.

- `/profile [player]` (also `/player`, `/cfn`): rank badge and Overview, Matchups, Rating, Habits and Replays tabs. Without a player, the caller's linked profile.
- `/me`: the caller's linked profile in this server.
- `/vs player [opponent]`: head-to-head record, recent results, character pairings and replays.
- `/leaderboard [character] [country] [scope]` and `/server-leaderboard`: global ladder, or only members who linked in this server.
- `/character name`: popularity, win rates, best and toughest matchups, top saved players.
- `/replay id`: one card whose primary button follows the replay's state: Watch, Capture replay, or Notify me.
- `/link [player]`: declare "this CFN profile is me" in this server. Links are per server; there is no verification, because a link only affects that server.
- `/alias set|remove|list`: private short names for players.
- `/queue`: the current capture queue.
- `/help`: a private guide.
- `/setup` (Manage Server): rank-up announcement channel and replay channel.
- Right-click a member → Apps → **SF Stats profile** or **Compare with me**.

Commands support server installs and user installs, and work in servers, DMs and
group DMs, except `/setup`, which needs the bot in the server.

## What the bot can see

- Interactions arrive over HTTPS, signed by Discord. Nothing is read from a gateway except the reaction gateway below.
- The reaction gateway requests only the `Guilds` and `GuildMessageReactions` intents. No privileged intents. It does not read chat messages, create captures, or send public messages.
- It only forwards a reaction when it is the 🔔 emoji, from a non-bot user, on a message in the one configured channel of the one configured server. Everything else is dropped before any network call.
- Logs are fixed strings. Discord user IDs, tokens, and interaction URLs are never logged; discord.js error objects are not printed because they can contain request paths.

## Running the reaction gateway

Requirements: Node 20 or newer, and a backend that accepts
`POST http://127.0.0.1:3010/internal/discord/reactions` with
`Authorization: Bearer <SFSTATS_INTERNAL_SECRET>` and a JSON body of
`{ messageId, userId, subscribed }`. The backend owns message-to-replay
validation and subscription changes, and reconciles reactions periodically to
cover any events missed while the gateway was down.

```sh
npm ci
cp .env.example .env   # fill it in; never commit it
set -a; . ./.env; set +a
npm run gateway
```

Expect `Discord reaction gateway ready`. Delivery is serialized so a slow add can
never overwrite a later removal; transient backend errors are retried four times
with backoff and then left to the backend's reconciliation. `SIGTERM` drains the
queue before exit. A systemd user unit example is in `deploy/systemd/`.

## Registering commands and emojis

Run both from a shell that has the variables from `.env.example` loaded. Never
pass the token as an argument.

```sh
npm run register
```

This upserts every command in `commands` globally, deletes the ones listed in
`retired`, and removes home-server copies of our own commands (they would
duplicate the globals in Discord's picker). Unrelated commands are left alone.

```sh
npm run emojis            # upload missing emojis
npm run emojis -- --replace   # re-upload all of ours after redesigning icons
```

Emoji names are `sf_<icon>` (from `icons.json`), `c_<character>` and `r_<rank>`.
The character portraits and rank badges are Capcom assets and are **not**
included in this repository; drop your own PNGs into
`public/profile-assets/v2/characters/` and `public/ranks/` (as `rank<N>_s.png`)
if you want those two families. Without them only the `sf_*` icons are uploaded.

## Tests

```sh
npm test
npm run typecheck
```

## License

MIT. Street Fighter, Buckler's Boot Camp and Capcom are trademarks of their
respective owners; the license grants no rights to third-party trademarks,
data or assets. This project is unofficial and not affiliated with Capcom.
