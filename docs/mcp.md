---
layout: default
title: AI / MCP Access
description: Let a compatible AI client manage your proxy's rules, feeds, and saved configuration.
permalink: /mcp/
---

**MCP** is a standard way to give an AI assistant specific tools. This project's MCP lets Codex, Claude Code, Claude Desktop, or another client that supports **local stdio MCP servers** read and change your proxy configuration. It uses the same authenticated manager API as the browser UI.

The MCP code and Docker image are public; your manager, credentials, and configuration do not need to be public. This is a local command launched by your AI client, **not** a new public web endpoint. Cloud-only clients that require a remote HTTP MCP URL cannot connect to this stdio server directly.

## What the AI Can Do

| Tools | What they allow |
| --- | --- |
| `get_overview`, `get_rules` | Read redacted settings, feeds, upstreams, and any rule profile |
| `put_custom_rule` | Create/edit a custom rule with its action, search scope, and upstream |
| `set_rule_lock`, `update_builtin_rule` | Unlock/relock a rule and edit built-in settings, not the underlying algorithm |
| `delete_custom_rule`, `replace_rules` | Delete one unlocked custom rule or import a complete rule profile |
| `set_connection`, `set_routing_tags` | Change saved URLs, keys, and existing Anime/TV tag labels |
| `put_feed`, `discover_prowlarr_indexers` | Create/edit feeds and refresh the proxy's saved upstream list |
| `test_connection`, `sync_feeds_to_sonarr` | Test saved Arr connections and explicitly synchronize owned Sonarr indexers |

There are **no** tools for editing app code, running commands, accessing files, deploying containers, changing Docker/Compose, downloading releases, or configuring Radarr. App maintenance belongs to your own development/deployment tools, not this public MCP.

## 1. Prepare a Private MCP Settings File

Start and configure the manager using your [OS installation guide]({{ '/installation/' | relative_url }}) first. Update it to a build with MCP support. Pull the image on the computer where the AI client runs:

```sh
docker pull ghcr.io/deepdaddyttv/sonarr-proxy-manager:latest
```

Download [mcp.env.example]({{ '/assets/examples/mcp.env.example' | relative_url }}) and save a private copy as `mcp.env`. It is separate from the manager's `.env`. Enter the same manager username/password you use in the browser; these are **not** the Sonarr/Prowlarr API keys.

```dotenv
MCP_MANAGER_URL=http://host.docker.internal:8787
MCP_AUTH_USERNAME=your-manager-login
MCP_AUTH_PASSWORD=your-manager-password
MCP_ALLOW_WRITES=false
MCP_SONARR_API_KEY=
MCP_PROWLARR_API_KEY=
MCP_PROXY_API_KEY=
```

Replace the login placeholders privately. Do not paste credentials into AI chat or commit `mcp.env`. Docker's env-file format expects literal values: do not surround passwords with quotes. Do not mount the manager's data volume or Docker socket into the MCP container; it communicates through the manager API instead.

Choose the manager URL **as the MCP process sees it**:

| How the MCP is launched | Manager URL / launch option |
| --- | --- |
| Docker Desktop on Windows/macOS, manager published on that host | `http://host.docker.internal:8787` |
| Docker Engine on Linux, manager published/listening on host loopback | Set `MCP_MANAGER_URL=http://127.0.0.1:8787`; add `--network host` to Docker arguments |
| Container sharing `sonarr-net` with the manager | `http://sonarr-proxy-manager:8787`; add `--network sonarr-net` |
| Local Python process on the manager's computer | `http://127.0.0.1:8787` |
| Manager on a different computer | Its reachable private HTTPS/LAN/VPN address, without `/manager/` |

For HTTP examples, the manager must use `AUTH_COOKIE_SECURE=false`. An HTTPS-only secure session cookie will not work through HTTP. If using HTTPS, use a trusted certificate and the same private route you use for the manager; certificate checks are not disabled.

## 2. Connect Codex

Add an entry to Codex's MCP configuration, replacing `/absolute/path/to/mcp.env` with your file's full path. See [OpenAI's MCP setup reference](https://developers.openai.com/codex/mcp/) for client-specific configuration. A downloadable [Codex TOML example]({{ '/assets/examples/mcp.codex.toml' | relative_url }}) is also available.

```toml
[mcp_servers.sonarr-proxy-manager]
command = "docker"
args = ["run", "--rm", "-i", "--env-file", "/absolute/path/to/mcp.env", "ghcr.io/deepdaddyttv/sonarr-proxy-manager:latest", "python", "mcp_server.py"]
tool_timeout_sec = 90
```

On Windows, use a full path such as `C:/Users/YOUR_USER/sonarr-proxy-manager/mcp.env` in the arguments. On Linux host networking, put `"--network", "host"` after `"-i"` and set the corresponding URL in `mcp.env`.

Restart/reconnect the client and ask: **"Use Sonarr Proxy Manager to list my feeds and read the rules for my Anime feed. Do not change anything yet."** You should see only three read/test tools while writes are disabled. If `docker` cannot be found by a desktop client, use the full path to its Docker executable in `command`.

## 3. Connect Claude

For Claude Code, register the same local command. Replace the private env-file path:

```sh
claude mcp add --transport stdio sonarr-proxy-manager -- docker run --rm -i --env-file /absolute/path/to/mcp.env ghcr.io/deepdaddyttv/sonarr-proxy-manager:latest python mcp_server.py
```

For Windows PowerShell, the same single-line command works with a quoted Windows path in place of `/absolute/path/to/mcp.env`. For Linux host-loopback access, add `--network host` after `-i`.

For Claude Desktop, merge this entry into your existing `mcpServers` object rather than replacing other servers. Download the [JSON example]({{ '/assets/examples/mcp.claude-desktop.json' | relative_url }}):

```json
{
  "mcpServers": {
    "sonarr-proxy-manager": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--env-file", "/absolute/path/to/mcp.env", "ghcr.io/deepdaddyttv/sonarr-proxy-manager:latest", "python", "mcp_server.py"]
    }
  }
}
```

Windows JSON paths can use forward slashes (`C:/Users/YOUR_USER/...`) or escaped backslashes (`C:\\Users\\YOUR_USER\\...`). Restart/reconnect Claude and inspect its MCP tools. See [Anthropic's MCP guide](https://code.claude.com/docs/en/mcp) for registration and approvals in Claude Code.

Use `-i`, **not** `-it` or `-d`: the AI client exchanges messages over stdin/stdout. The MCP process does not start another manager or publish a port. You can replace `latest` with `dev` or a successful `build-<number>` tag in any example.

## 4. Allow Changes When Ready

Change `MCP_ALLOW_WRITES=true` in your private `mcp.env` and restart the MCP connection. All thirteen tools will then be available. This switch applies to the MCP only; it does not disable editing in the browser UI.

Keep your AI client's approval prompts enabled. The server marks write/destructive tools, but the client controls human approval. A `confirm=true` argument is an additional guard for deleting a rule, replacing a full profile, clearing a key, or syncing Sonarr; it is **not** a substitute for the client actually asking you first.

For example:

> In my Lime TV feed, add an enabled custom rule named "Exclude CAM", matching the literal text "CAM", with action Exclude, scope Episodes, and only the LimeTorrents upstream. Preserve all other rules and do not sync Sonarr.

The assistant should read `get_overview`, use the real feed/source IDs it returns, read `get_rules` for that feed, and pass the returned `revision` to `put_custom_rule`. The API rejects stale revisions, so a concurrent change requires another read. Matches are case-insensitive literal text, not regular expressions. Rules affect future searches; they do not remove existing media.

Built-ins remain locked by default. To edit one, the assistant must use `set_rule_lock` first, then edit it using the **new** revision, and optionally lock it again. A complete-profile import also respects existing locks.

Creating or editing a feed does **not** automatically change Sonarr. Review the saved feeds, then explicitly approve `sync_feeds_to_sonarr` if you want their Sonarr entries added/updated. The proxy preserves unrelated Prowlarr-managed entries.

## Change Connections Without Sharing Secrets in Chat

Leave the optional MCP API-key variables blank unless you need to replace a saved key. To supply a new key, put it privately in `MCP_SONARR_API_KEY`, `MCP_PROWLARR_API_KEY`, or `MCP_PROXY_API_KEY`, restart the MCP connection, and ask the assistant to load that service's key **from the environment**. `set_connection` accepts a load flag, not a raw key argument. Returned settings report whether a key exists, never its value.

Settings supplied by the **manager's** Compose/environment are still read-only. The MCP cannot override them or change the manager login, container ports, image, or baked-in algorithms. Edit those through your normal deployment workflow.

Configuration and rule text will be visible to the AI service you choose, even though credentials are omitted. Connect only trusted clients and do not put secrets into rule names, descriptions, or match values.

## Optional: Run from Source

If you prefer not to launch another container, install Python 3.10 or newer and the pinned MCP dependency in a virtual environment:

```sh
python -m venv .venv
# Activate .venv using your OS's normal virtual-environment command.
python -m pip install -r requirements-mcp.txt
python mcp_server.py
```

Supply `MCP_MANAGER_URL`, `MCP_AUTH_USERNAME`, `MCP_AUTH_PASSWORD`, and optionally `MCP_ALLOW_WRITES` through the client process environment. The Python script does not automatically read `mcp.env`; Docker's `--env-file` does that in the earlier examples. Configure the AI client to launch the virtual environment's Python with the script's full path. Running it alone in a terminal simply waits for an MCP client.

## Troubleshooting

- **Only three tools:** writes are disabled. Set `MCP_ALLOW_WRITES=true` and reconnect if you want editing.
- **Authentication fails:** use the manager login, not an Arr key; verify HTTP/HTTPS matches the manager's secure-cookie setting.
- **Cannot reach the manager:** use the address for the MCP process's network, not necessarily your browser URL. Desktop hostnames and Linux host networking are different.
- **Configuration changed:** read the rules/feeds again; do not blindly retry an old full configuration.
- **Setting cannot be changed:** it may be locked or controlled by the manager environment. Unlock rules separately; environment values need a deployment change.
- **Cloud client asks for an MCP URL:** this release is stdio-only. Use a compatible local client rather than exposing the manager on the internet.

Return to [Custom Rules]({{ '/rules/' | relative_url }}) for actions and examples, or [Connections]({{ '/connections/' | relative_url }}) for manual setup.
