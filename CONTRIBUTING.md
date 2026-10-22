# Contributing

Issues and pull requests are welcome.

- Run `npm test` and `npm run typecheck` before opening a pull request.
- Keep the bot's privacy stance: no privileged intents, no reading chat messages,
  no logging of user IDs or tokens. Changes that widen what the bot can see need
  a written reason in the pull request.
- Never commit a `.env`, a token, a cookie, or real Discord IDs from a server
  you do not own.
- Command definitions in `scripts/register-discord-commands.mjs` are the public
  contract. A new or renamed command needs matching handling in the backend
  before it is registered, so open an issue first.
