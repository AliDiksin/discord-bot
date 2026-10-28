# SF Stats - Street Fighter 6 Stats and Fighting Game Frame Data

A Discord bot with two sides: Street Fighter 6 player stats from [sfstats.app](https://sfstats.app) (profiles, matchups, leaderboards, replays) and instant frame data, hitbox images, combo routes and quizzes for 11 fighting games. Ask in plain words, use slash commands, or browse with menus. The frame data side was previously its own bot, FrameBub.

## Features

### Player stats (sfstats.app)
- **Player Cards** - `/profile` shows a player's rank, recent form, matchups, rating, habits and replays in tabs
- **Your Profile** - `/link` says which CFN profile is you in a server; `/me` then opens your card and commands default to you
- **Head-to-Head** - `/vs` shows the record between two players, recent results and character pairings
- **Leaderboards** - `/leaderboard` by character and country, globally or in this server; `/server-leaderboard` ranks only members who linked
- **Characters** - `/character` shows popularity, win rates, best and toughest matchups and top players
- **Replays** - `/replay` follows a replay: watch it, request a capture, or get a DM when it's ready; `/queue` shows captures in progress
- **Plain Words** - `@SF Stats my rank` or `@SF Stats daigo replays` answers with the matching card
- **Right-Click Shortcuts** - right-click a member, then Apps, for **SF Stats profile** or **Compare with me**
- **Server Setup** - `/setup` (Manage Server) picks channels for rank-up announcements and replay captures

### Frame data
- **Natural Language Lookup** - Ask questions like `what is the framedata for ryu's fireball?` or `ryu vs ken 5hp` in plain English
- **11 Supported Games** - SF6, SFV, USF4, GGST, GGACR, 2XKO, BBCF, COTW, Third Strike, MK1 and AVTL
- **Hitbox Images** - Frame cards show hitbox or move images from each game's wiki; for SF6, ask for `gif` for an animated hitbox
- **Compare Moves** - Press Compare to pick a second move and view both side by side
- **Rankings** - With a Decisions API key set (`DECISIONS_API_KEY`), ask for "the move with the most range", "fastest normal" or "Ken's most plus move on block"
- **Interactive Menu** - `/sfstatsmenu` opens a game, character and move selector for every game
- **Slash Commands** - Dedicated `/sf6`, `/sfv`, `/usf4`, `/ggst`, `/ggacr`, `/2xko`, `/bbcf`, `/cotw`, `/third-strike`, `/mk1` and `/avtl` commands
- **Combos and Stats** - `/sf6-combos`, `/mk1-combos` and `/sf6-stats` (character stat sheets)
- **Glossary** - `/glossary` explains fighting game terms, with a link to Infil's Fighting Game Glossary
- **Quiz Mode** - Test your knowledge with easy, medium and hard frame data quizzes across all games
- **Notes Toggle** - View move-specific notes from community wikis and frame data sources

`/readme` is a quick guide to both sides; `/help` is SF Stats' full guide to the player stats commands.

## Supported Games

| Game | Source | Notes |
|------|--------|-------|
| Street Fighter 6 | FAT ODS | SuperCombo hitbox images, character stats, combo routes |
| Street Fighter V | FAT ODS | V-Trigger separated rows, SuperCombo images |
| Ultra Street Fighter IV | SuperCombo ODS | 44-character roster, source notes, available move images |
| Guilty Gear Strive | Dustloop ODS | Hitbox images, state-specific moves (Installs, Blood, etc.) |
| Guilty Gear Accent Core Plus R | Dustloop ODS | Hitbox images, move notes |
| 2XKO | Community ODS | Wiki-sourced images and hitboxes |
| BlazBlue Central Fiction | Dustloop ODS | Hitbox images, move notes |
| City of the Wolves | DreamCancel ODS | Regular move images (no hitbox images available) |
| Third Strike | SuperCombo ODS | Hitbox images, versioned moves |
| Mortal Kombat 1 | Kombat Akademy | Playable characters, Kameos, combo routes |
| Avatar Legends: The Fighting Game | SuperCombo ODS | Hitbox images, move notes |

## Screenshots

| Natural Language | Menu System | Frame Data Table |
|:---:|:---:|:---:|
| <img width="400" alt="Natural language queries" src="https://github.com/user-attachments/assets/83ffd010-2605-4d66-97ae-09f8ed18bff9" /> | <img width="400" alt="Frame data menu" src="https://github.com/user-attachments/assets/099056f2-a4f4-480f-97d6-c7f1f064b977" /> | <img width="400" alt="Frame data table" src="https://github.com/user-attachments/assets/afe309e9-efb6-4efb-854a-f57b1cd575f6" /> |
| <img width="400" alt="Natural language query 2" src="https://github.com/user-attachments/assets/eb99c148-fcb1-4db9-9db7-a43b26fafb9c" /> | <img width="400" alt="Menu game select" src="https://github.com/user-attachments/assets/dadbef81-8e10-4f51-8ba1-2b24f7e2584e" /> | <img width="400" alt="Frame data table 2" src="https://github.com/user-attachments/assets/d6d93bf6-ff69-467e-a328-70a74c9e55c1" /> |
| <img width="400" alt="Natural language query 3" src="https://github.com/user-attachments/assets/7105b5dc-d411-4096-8427-1b31b46e5880" /> | <img width="400" alt="Menu character select" src="https://github.com/user-attachments/assets/1d54d8b2-e13a-46ee-b553-dc6504e03214" /> | <img width="400" alt="Frame data table 3" src="https://github.com/user-attachments/assets/5cbe2769-0886-4926-9ef9-bf8c2fb253c8" /> |

These predate the rename to SF Stats.

## Quick Reference

### Plain-Language Examples
```
@SF Stats my rank
@SF Stats daigo replays
@SF Stats ryu 5hp framedata
@SF Stats ken fireball gif
@SF Stats mai ex fan
@SF Stats 3s urien 5hp and 2mk
@SF Stats usf4 cammy cannon spike lk framedata
@SF Stats mk1 sub 1 framedata
@SF Stats ahri 5l vs ken 5p
```

### Player Stats Commands
| Command | Example |
|---------|---------|
| `/profile` | `player: Daigo` (no player: your linked profile) |
| `/vs` | `player: Daigo` `opponent: Tokido` |
| `/leaderboard` | `character: Ryu` `country: Japan` |
| `/character` | `name: Ken` |
| `/replay` | `id:` a replay ID from sfstats.app |
| `/link` | `player:` your CFN name |
| `/alias set` | `name: daigo` `player:` his profile |

### Frame Data Commands
| Command | Example |
|---------|---------|
| `/sfstatsmenu` | Opens the menu |
| `/sf6` | `char_name: Ryu` `move_name: 236LP` |
| `/ggst` | `char_name: Ky` `move_name: 5H` |
| `/ggacr` | `char_name: Sol Badguy` `move_name: 236P` |
| `/sfv` | `char_name: Ryu` `move_name: 5MP` |
| `/2xko` | `char_name: Ahri` `move_name: 5L` |
| `/bbcf` | `char_name: Ragna` `move_name: 5B` |
| `/cotw` | `char_name: Ronaldo` `move_name: Far C` |
| `/third-strike` | `char_name: Urien` `move_name: 5HP` |
| `/usf4` | `char_name: Cammy` `move_name: Cannon Spike (623 LK)` |
| `/mk1` | `char_name: Sub-Zero` `move_name: 1` |
| `/avtl` | `char_name: Korra` `move_name: 236A` |

## How It Works

The bot is one Discord application that receives everything over the gateway. Frame data is answered here, from the workbooks in this folder. Player stats commands, buttons and forms are forwarded unchanged to sfstats.app, which answers them with the same handlers as its signed interactions (`bubbot/runtime/sfstats_bridge.py`). Plain-language messages addressed to SF Stats go there too, and anything that is frame data is answered with this bot's data (`bubbot/runtime/sfstats_messages.py`). Without the `SFSTATS_*` settings the bot runs as frame data only.

## Setup

### Prerequisites
- Python 3.13 or newer
- A Discord bot token
- The ODS frame data files (included in this folder)

### Installation
```bash
git clone https://github.com/sfstatsapp/discord-bot.git
cd discord-bot/bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration
Copy `.env.example` to `.env` and fill it in. Only `DISCORD_TOKEN` is required;
the `SFSTATS_*` settings connect the bot to [SF Stats](https://sfstats.app) and are
explained in the file. Never commit `.env`.

### Running
Run from this folder: the frame data loaders read the workbooks relative to it.
```bash
python bot.py
```

## Project Structure

```
bubbot/
  runtime/          # Bot entrypoint, message routing, slash commands, the SF Stats link
  frame_data/       # Per-game parsers, embeds, and lookup helpers
  features/         # Menus, quiz, glossary, failure cards and issue reports
  data/             # Alias maps, generated image caches, SF Stats command definitions
  utils/            # Shared text, comparison, Discord helpers
scripts/            # Cache builders, scrapers, deploy and sync tools
tests/              # unittest suites
mk1/                # MK1 JSON source data
*.ods               # Frame data source files (one per game)
```

## License

MIT
