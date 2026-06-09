# agent-launcher

A Pokemon-style terminal TUI launcher for [Codex CLI](https://github.com/openai/codex) and [Claude Code](https://github.com/anthropics/claude-code).

Walk around a pixel map, approach relay station profiles, and launch your AI agent of choice.

![Python](https://img.shields.io/badge/python-3.8+-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)

## Demo

https://github.com/user-attachments/assets/0fc92831-c69e-4243-826a-7b34e3cdd522

## Features

- Pokemon-style map — walk up to a profile ball to interact
- Supports both **Codex** and **Claude Code** relay configs
- Per-profile relay config (URL + API key) for each agent
- Built-in `✦` new-profile ball — add profiles without leaving the game
- Split-screen layout: left = game map, right = live status panel
- Auto-backups before every config switch
- Launches agent directly via `exec` — no wrapper process

## Requirements

- Python 3.8+ (stdlib only, no dependencies)
- macOS
- [Codex CLI](https://github.com/openai/codex) and/or [Claude Code](https://github.com/anthropics/claude-code) installed

## Installation

```bash
git clone https://github.com/yourname/agent-launcher.git
cd agent-launcher

# Add alias
echo "alias agent-launcher='python3 $(pwd)/launcher.py'" >> ~/.zshrc
source ~/.zshrc
```

## Usage

```bash
agent-launcher
```

### Controls

| Key | Action |
|-----|--------|
| `W` `A` `S` `D` / `↑↓←→` | Move character |
| `Space` / `Enter` | Interact with nearby profile ball |
| `P` | Open profiles manager |
| `Q` | Quit |

In profile editor:

| Key | Action |
|-----|--------|
| `↑` `↓` | Move between fields |
| `Enter` | Edit selected field |
| `S` | Save profile |
| `Esc` | Cancel |

### Workflow

1. Run `agent-launcher`
2. Walk to the green `✦` ball to add your first relay profile
3. Fill in a name, URL and API key for Codex and/or Claude
4. Walk to the profile ball that appears, press Space
5. Choose **Launch Codex** or **Launch Claude**

### Profile storage

Profiles are saved to `~/.agent-launcher/profiles.json`. They are never stored in the project directory.

```json
[
  {
    "name": "my-relay",
    "codex":  { "url": "https://example.com/v1",        "key": "sk-..." },
    "claude": { "url": "https://example.com/anthropic",  "key": "tp-..." }
  }
]
```

Backups of modified config files are stored in `~/.agent-launcher/backups/`.

## How it works

On launch, `launcher.py` writes the selected profile's config to:

**Codex** — `~/.codex/config.toml` + `~/.codex/auth.json`
```toml
model_provider = "custom"
preferred_auth_method = "apikey"

[model_providers.custom]
base_url = "https://your-relay.com/v1"
```

**Claude Code** — `~/.claude/settings.json`
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://your-relay.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "tp-..."
  }
}
```

Then replaces itself with the agent process via `os.execv`.

## License

MIT
