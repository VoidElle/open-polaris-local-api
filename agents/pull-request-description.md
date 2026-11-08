# Pull Request Description Agent — open-polaris-local-api

## Purpose
Generate clear, structured PR descriptions for this async Python TCP IoT library.

## PR Description Template

### Title format
`[scope]: short imperative description`

Scopes: `client`, `models`, `exceptions`, `docs`, `chore`

### Body structure
```
## What
[1–2 sentences: what changed and why]

## How
[Brief explanation of the approach, especially for protocol or async changes]

## Testing
[How the change was validated — manual test against device, unit test, etc.]

## Breaking Changes
[List any breaking changes, or "None"]
```

## Domain Context
- **TCP protocol**: each command opens/closes its own socket — changes to `_send_and_receive` affect all commands; call out explicitly
- **`stato_r` fallback**: the `get_status()` fallback path (`res=4` → full `stato`) is a critical reliability mechanism — flag if removed or weakened
- **Model field mapping**: `from_local()` handles three dialects (ridotto / full / cloud PascalCase) — changes to field key lookup may silently break one dialect; test all three
- **`t_can` encoding**: stored as °C, transmitted as `°C × 10` — changes to this conversion are high-risk
- **`fan_set` / `shu_set` coupling**: protocol always sends both with the same value; breaking this will cause partial device updates
- **Write commands with no response**: `upd_zona` and `upd_cu` do not always return a response — code must treat `None` result as a warning, not an error
- **`_device` being `None`**: write methods must guard against `_device=None` (no prior `async_update`) — flag any PR that removes these guards
- **Error bitmask messages**: `_CU_ERROR_MESSAGES` and `_ZONE_ERROR_MESSAGES` are derived from APK strings — never change indices; only add new entries at the end
- **No third-party deps**: stdlib only — reject any PR adding external packages
- **Python 3.11+**: do not use `asyncio.iscoroutinefunction()` (deprecated 3.14) — use `inspect.iscoroutinefunction()`
