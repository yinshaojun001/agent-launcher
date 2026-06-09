# codex-launcher

A terminal TUI launcher for [Codex CLI](https://github.com/openai/codex) that manages multiple relay station profiles and switches between them before launching Codex.

![Python](https://img.shields.io/badge/python-3.8+-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)

## Features

- Switch between multiple API relay stations before launching Codex
- Saves relay profiles (URL + API key) locally
- Marks the currently active relay with `●`
- Delete unused profiles with `d`
- Auto-backs up `config.toml` and `auth.json` before every switch
- Launches Codex directly via `exec` — no wrapper process

## Requirements

- Python 3.8+
- [Codex CLI](https://github.com/openai/codex) installed

## Installation

```bash
# Clone
git clone https://github.com/yourname/codex-launcher.git
cd codex-launcher

# Make executable
chmod +x launcher.py

# Add alias (add to ~/.zshrc or ~/.bashrc)
echo "alias codex-launcher='python3 $(pwd)/launcher.py'" >> ~/.zshrc
source ~/.zshrc
```

## Usage

```bash
codex-launcher
```

### Key bindings

| Key | Action |
|-----|--------|
| `↑` / `↓` or `k` / `j` | Move selection |
| `Enter` | Confirm |
| `d` | Delete selected profile |
| `q` / `Esc` | Cancel / go back |

### Workflow

1. Run `codex-launcher`
2. Select **Switch relay** to pick or add a relay station
3. Select **Launch Codex** — Codex starts with the selected relay config

### Profile storage

Profiles are saved to `~/.codex/relay-profiles.json`:

```json
[
  {
    "name": "my-relay",
    "url": "https://example.com/v1",
    "key": "sk-..."
  }
]
```

Backups of `config.toml` and `auth.json` are stored in `~/.codex/.auth-backups/`.

## How it works

On relay switch, `launcher.py` updates three fields in `~/.codex/config.toml`:

```toml
model_provider = "custom"
preferred_auth_method = "apikey"

[model_providers.custom]
base_url = "https://your-relay.com/v1"
```

And writes the API key to `~/.codex/auth.json`. Then on launch it replaces itself with the Codex process via `os.execv`.

## License

MIT
