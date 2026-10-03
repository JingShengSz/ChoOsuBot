# mania-render node (Windows) — the machine that actually renders

The VPS is only a **relay**. Rendering happens here, on this Windows box.

```
   VPS (2 cores, ~6.4 fps)                       This machine (32 threads, ~47.7 fps)
   ┌──────────────────────────────┐              ┌──────────────────────────────────┐
   │ astrbot.service              │              │ mania_render --web --port 8760   │
   │   plugin config:             │              │   bound to 127.0.0.1:8760        │
   │   server = 127.0.0.1:8760 ───┼──┐           │   engine=webgl  ──►  Chrome      │
   │                              │  │           │            ▲          :9222    │
   │ sshd                         │  │           │            │       (CDP, GPU)   │
   │   127.0.0.1:8760  ◄──────────┼──┘  ═══════►│ ssh -N -R 8760:127.0.0.1:8760 ──┘ │
   │   (a reverse-forward listener│    reverse   │                                   │
   │    owned by sshd, NOT python)│    tunnel    │ Scheduled Task: ManiaRenderNode   │
   └──────────────────────────────┘              └──────────────────────────────────┘
```

`mania-render.service` on the VPS is **inactive + disabled** on purpose: it would fight the
tunnel for `127.0.0.1:8760`, and the whole point is that the VPS must not render.

## The three things the supervisor keeps alive

| # | What | Why it is supervised |
|---|---|---|
| 1 | `python -m mania_render --web --port 8760` | the service the tunnel forwards to |
| 2 | `ssh -N -R 8760:127.0.0.1:8760 root@<vps>` | makes the VPS's loopback port land here |
| 3 | **headless Chrome on `127.0.0.1:9222`** | the WebGL engine drives *that browser*; without it every WebGL job fails with 「连不上无头 Chrome」 |

All three are checked **before** a tunnel attempt and again **every 15 s while the tunnel is
up** (`-HealthEvery`). The earlier shape called the checks once and then sat in
`$proc.WaitForExit()` for as long as the tunnel held — a service or browser that died
mid-session stayed dead until the tunnel happened to drop.

### Chrome, and the flags that matter

```
chrome --headless=new --remote-debugging-port=9222
       --user-data-dir="<project>\cache\chrome-gpu-profile"
       --enable-gpu --use-angle=d3d11 --ignore-gpu-blocklist --enable-gpu-rasterization
       --no-first-run --no-default-browser-check about:blank
```

Measured on this machine (RTX 5060 Laptop), not assumed:

| flags | `UNMASKED_RENDERER_WEBGL` | draw speed |
|---|---|---|
| `--enable-gpu --use-angle=d3d11 --ignore-gpu-blocklist` | `ANGLE (NVIDIA, NVIDIA GeForce RTX 5060 Laptop GPU (0x00002D19) Direct3D11 …, D3D11)` | **259 fps** |
| `--use-angle=swiftshader --enable-unsafe-swiftshader` | software | **35 fps** |

so a Chrome that quietly fell back to software would still "work" and be ~7x slower. The
guard therefore checks **flags, not just that the port answers**: a browser on `:9222`
without `--use-angle=d3d11` (or with `swiftshader`) is killed and replaced. The profile
directory is quoted explicitly in the argument list — unquoted, the space in
`D:\DeepSeek Harness\…` split it into three positional arguments and Chrome refused to
start at all with *"Multiple targets are not supported in headless mode"*.

Verify what the browser is really using (flags are a claim; this is a measurement):

```powershell
python -m tools._engine_cutover.gpu_probe      # prints UNMASKED_RENDERER_WEBGL
```

## Files here

| File | What it is |
|---|---|
| `render-node.ps1` | The supervisor: keeps the render service, Chrome AND the tunnel alive, in a loop. |
| `run-hidden.vbs` | Launches the supervisor with **no console window**. |
| `install-task.ps1` | Registers/starts the `ManiaRenderNode` Scheduled Task (at logon). |
| `stop-node.ps1` | Stops the task, the supervisor, its ssh, the render service and our Chrome. |
| `node-launcher.ps1` | Backend of the two **Desktop launchers**: `-Action Start` starts the node and verifies it, `-Action Check` only reports. All the checks live here. |
| `clear-wedged-tunnel.sh` | Clears a **wedged** reverse-forward on the VPS (a dead session still holding `127.0.0.1:8760`). Run on the VPS; `node-launcher.ps1` invokes it automatically when `tunnel.log` shows the matching signature. |
| `e2e-webgl.sh` | End-to-end proof of the **WebGL** engine, run **on the VPS**: POST → poll → download → `ffprobe`. Optional 3rd arg = engine field. |
| `e2e-test.sh` | The earlier end-to-end proof (hardcoded `engine=python`, 1280x720). Kept for the Python engine. |
| `offline-harness.py` | Runs the deployed plugin's real `_render()` to print the exact chat text. |
| `logs/` | `supervisor.log`, `tunnel.log`, `render-service.{out,err}.log`, `chrome.{out,err}.log`. |

## After a reboot: the two Desktop launchers

```
C:\Users\OwO\Desktop\启动渲染节点.cmd    ->  node-launcher.ps1 -Action Start   (start + verify)
C:\Users\OwO\Desktop\检查渲染节点.cmd    ->  node-launcher.ps1 -Action Check   (status only)
```

Both are thin, **pure-ASCII** `.cmd` wrappers — cmd.exe decodes a `.bat` with the *console*
codepage, so Chinese in the wrapper would be mojibake — that call `node-launcher.ps1` with
`-ExecutionPolicy Bypass -NoProfile -File` and then `pause`, so the window cannot flash and
vanish before the result is readable. All the logic and all the Chinese live in
`node-launcher.ps1`, next to the node's other scripts, so the two Desktop files cannot drift
apart. Neither ever asks for administrator rights. (Write the `.ps1` as UTF-8 **with BOM**:
Windows PowerShell 5.1 reads a BOM-less file as ANSI and the Chinese turns to garbage.)

`-Action Start` is idempotent: if the supervisor is already alive it says so and starts
nothing. Otherwise it runs `Start-ScheduledTask ManiaRenderNode` — falling back to
`wscript run-hidden.vbs` if the task is not registered, and always saying which path it took
— then polls for up to 90 s.

Then, in both modes, five things are printed with ✓/✗:

| # | Check | How it is established |
|---|---|---|
| 1 | 渲染服务 `127.0.0.1:8760` | `GET /api/skins` → 200 |
| 2 | Chrome `127.0.0.1:9222` | CDP answers **and** the live `UNMASKED_RENDERER_WEBGL` is D3D11/NVIDIA. A SwiftShader browser is reported as a **FAILURE** — flags alone are only a claim |
| 3 | 隧道 | verified **from the VPS**: `ssh` + `curl` its own `127.0.0.1:8760`; the reply must carry this machine's `D:\…` skin paths, which is the only proof the bytes went through the tunnel |
| 4 | 上报 | the last successful heartbeat in `supervisor.log` (the blog's `/api/pc-status` is POST-only, so it cannot be read back) |
| 5 | 计划任务 | `Get-ScheduledTask ManiaRenderNode \| Select State` |

Exit code 0 when 渲染服务 + Chrome + 隧道 are all up, 1 otherwise. The status token is never
printed, and neither are window titles.

### The failure it is built around

If the Windows-side `ssh` dies without a clean FIN — a network drop, a suspend, or a
**reboot** — the VPS-side `sshd` child keeps the remote-forward listener it created on
`127.0.0.1:8760`. Connections are then *accepted and never answered*, and the next tunnel
dies with:

```
Error: remote port forwarding failed for listen port 8760
```

so the node can never come back on its own. `node-launcher.ps1` recognises that signature and
runs `clear-wedged-tunnel.sh`, which kills **only the sshd owning that listener** — never the
master daemon, never another session (the user's `-L 6185` / `-L 6099` tunnel is a different
sshd), and never `mania-render.service`, AstrBot, NapCat, UFW or nginx. Note that a *clean*
process kill does not leave this corpse; it is specifically the unclean ones.


## Why `ssh -R 8760:127.0.0.1:8760` lands on *this* machine

`ssh -R` forwards the **remote** listener to a target on the **local** side, so
`-R 8760:127.0.0.1:8760` means: *listen on the VPS's 8760, deliver to 127.0.0.1:8760 of the
machine running ssh* — this one. The VPS's sshd has `GatewayPorts` at its default `no`, so
that listener binds to the VPS loopback only. Verified, not assumed:

```
$ ss -lntp | grep 8760            # on the VPS
LISTEN 0 128 127.0.0.1:8760 0.0.0.0:* users:(("sshd",pid=...))
LISTEN 0 128    [::1]:8760    [::]:* users:(("sshd",pid=...))
$ curl http://www.liuliyue.com:8760/  # via the public hostname -> refused
```

## Why not autossh

`autossh` is not available on Windows. `render-node.ps1` is the equivalent: run `ssh` in
the foreground of a loop, and when it exits, log why and restart it with exponential
backoff (3 s → 60 s, reset after a session that lasted ≥ 120 s). ssh is given
`ServerAliveInterval=30 ServerAliveCountMax=3` so it notices a dead path within ~90 s, and
`ExitOnForwardFailure=yes` so it exits rather than lingering without a forward.

## Supervisor mechanism and its honest limitations

**Mechanism:** a Scheduled Task `ManiaRenderNode` with an **AtLogOn** trigger for the
current user, running `wscript.exe run-hidden.vbs`, which starts `powershell.exe` with
`WScript.Shell.Run(cmd, 0, True)`.

Two non-obvious details, both of which bit us and are load-bearing:

1. **`wait = True` in the VBS.** Task Scheduler puts a task's processes in a job object and
   tears that job down as soon as the task's *action* process exits. With `wait = False`,
   wscript returns immediately, the task counts as finished, and Task Scheduler then kills
   the supervisor — plus its ssh and the render service. Symptom: `LastTaskResult=0` with no
   process and no log anywhere. Waiting keeps wscript alive as long as the supervisor runs.
2. **`$PSScriptRoot` is NOT available in a `param()` default under Windows PowerShell 5.1.**
   `[string] $LogDir = (Join-Path $PSScriptRoot 'logs')` therefore evaluated to
   `Join-Path '' 'logs'` and threw *"Cannot bind argument to parameter 'Path' because it is
   an empty string"* before a single line ran. `pwsh` 7 populates it, which is why the script
   tested fine in the foreground and died under the task. Resolved in the body instead.

**Limitations, stated plainly:**

- It starts **after the user logs in**, not at boot. Nothing renders while nobody is logged
  on. A boot-time task needs either an administrator or a stored credential — see below.
- No console window appears (`MainWindowHandle = 0` for both `wscript.exe` and
  `powershell.exe`), but the task therefore also shows as permanently **Running** in Task
  Scheduler. That is intended: it doubles as a status light.
- If the supervisor is killed without its children, the next start's `-KillStaleTunnels`
  cleans up any leftover ssh holding `-R 8760:` (other tunnels, e.g. `-L 6185`, are never
  touched).

### Stop / restart / status

```powershell
# status
Get-ScheduledTask ManiaRenderNode | Select TaskName,State        # Running == node is up
Get-Content tools\render-node\logs\supervisor.log -Tail 20

# restart
pwsh -File tools\render-node\stop-node.ps1      # keep the task, stop the node
Start-ScheduledTask ManiaRenderNode

# stop completely AND uninstall the task
pwsh -File tools\render-node\stop-node.ps1 -RemoveTask

# (re)install
pwsh -File tools\render-node\install-task.ps1
```

### Making it run at boot instead of logon

Not possible for an unelevated user without a stored credential. Measured on this machine:

```
$ schtasks /Create /TN probe /SC ONSTART /RU SYSTEM /TR "wscript.exe ..."
ERROR: Access is denied.                      # IsInRole(Administrator) = False
```

An `AtStartup` task must run as SYSTEM or with "run whether user is logged on or not"; the
latter needs the account password stored with the task. From an **elevated** shell:

```powershell
# system copy of the key with restrictive ACLs, then a boot task running as SYSTEM:
$dest = 'C:\ProgramData\mania-render\id_ed25519'
New-Item -ItemType Directory -Force C:\ProgramData\mania-render | Out-Null
Copy-Item "$env:USERPROFILE\.ssh\id_ed25519" $dest
icacls $dest /inheritance:r /grant:r "SYSTEM:R" "Administrators:R"

$action  = New-ScheduledTaskAction -Execute 'wscript.exe' `
             -Argument '"D:\DeepSeek Harness\workspace\osu-mania-render\tools\render-node\run-hidden.vbs" -SshKey "' + $dest + '"'
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName ManiaRenderNodeBoot -Action $action -Trigger $trigger `
  -Principal $principal -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0))
```

Note SYSTEM has no `%USERPROFILE%`, so `-SshKey` must be passed explicitly, and
`StrictHostKeyChecking=accept-new` (already set) is what avoids a first-run host-key prompt.
The render service itself also needs a Python with Pillow+numpy reachable by SYSTEM — the
supervisor probes several interpreters and logs which one it picked.

## Diagnosing

```powershell
Get-Content tools\render-node\logs\supervisor.log -Tail 30   # reconnects, backoff, service + chrome starts
Get-Content tools\render-node\logs\tunnel.log     -Tail 30   # ssh's own stderr per attempt
Get-Content tools\render-node\logs\render-service.out.log   # render progress + `[engine] job=… engine=…`
Get-Content tools\render-node\logs\render-service.err.log   # tracebacks
Get-Content tools\render-node\logs\chrome.err.log           # only when the supervisor launched Chrome
Get-Content cache\api.log -Tail 40                          # per-request trace, incl. every stream upload
```

Which engine actually ran is in two places, because a silent fallback to the other renderer
looks exactly like a success otherwise:

```
logs\render-service.out.log:  [engine] job=aa6629472263 engine=webgl
cache\api.log:                engine job=aa6629472263 engine=webgl
```

From the VPS:

```bash
ss -lntp | grep 8760                       # a listener here means the tunnel is up
curl -s http://127.0.0.1:8760/api/skins    # paths starting D:\ prove it is the Windows box
journalctl -u astrbot -f | grep mania      # plugin-side view
```

## "Refuse if offline" — the behaviour is deliberate

There is **no server-side fallback renderer**. If this machine stops, or the tunnel drops,
the VPS's `127.0.0.1:8760` has no listener, the plugin's HTTP call fails, and the render is
**refused** with a message that says so:

```
渲染服务不可达：本机渲染节点似乎离线（隧道未建立）。
渲染固定在本机完成，服务端不会回退渲染——请等本机上线后重试。
```

That is produced by `RENDER_NODE_OFFLINE` in the plugin's `main.py`, reached whenever
`_is_unreachable(exc)` classifies the failure as a connection error rather than an HTTP/API
error. The raw cause is logged at ERROR level next to it, e.g.

```
[mania] 渲染节点不可达（http://127.0.0.1:8760）: Cannot connect to host 127.0.0.1:8760
ssl:default [Connect call failed ('127.0.0.1', 8760)]
```

It is raised from three places: the skin-list call, the `POST /api/render`, and — after
`POLL_UNREACHABLE_LIMIT` (6) consecutive failed polls, ~30 s — mid-render job polling, so a
node that dies during a render is not waited on for the full 1800 s.
