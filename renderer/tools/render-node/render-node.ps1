<#
    mania-render node supervisor  (Windows)
    ======================================

    This machine is the render node. The VPS is only a relay: its own 127.0.0.1:8760 is a
    reverse SSH tunnel endpoint that lands HERE.

    Two things are supervised, both locally:
      1. the render service   python -m mania_render --web --port 8760   (pinned to 127.0.0.1)
      2. the reverse tunnel   ssh -N -R 8760:127.0.0.1:8760 root@<vps>

    and a third that the render service depends on:
      3. headless Chrome on 127.0.0.1:9222 with the GPU flags -- the WebGL engine drives
         THAT browser over CDP. Without it every WebGL job fails with "连不上无头 Chrome",
         and nothing else on this machine brings it back.

    and a fourth that is not a guard but a reporter (added 2026-09-29):
      4. the local-PC status heartbeat POSTed to the blog every 60 s, which feeds the
         "主机状态" panel in the blog's homepage sidebar. See the STATUS REPORTER
         section below. It is deliberately part of THIS loop rather than a second
         process: one supervisor, one thing to keep alive, and it can never outlive
         the node it reports on.

    Nothing is supervised on the VPS. mania-render.service there is deliberately DISABLED
    (systemctl disable --now mania-render) so it cannot re-grab the port the tunnel needs.
    The AstrBot plugin has NO server-side fallback renderer: if this machine or the tunnel
    is down the render is REFUSED. That is the designed behaviour, not a bug to paper over.

    How the VPS reaches the local service
    -------------------------------------
    `ssh -R` forwards the REMOTE listener to a target on the LOCAL side, so
        -R 8760:127.0.0.1:8760
    means "listen on the VPS's 8760, deliver to 127.0.0.1:8760 of the machine running ssh"
    -- i.e. this one. The VPS's sshd has GatewayPorts at its default `no`, so the listener
    binds to the VPS loopback only (verified: ss shows 127.0.0.1:8760 and [::1]:8760, and
    the public IP refuses the connection).

    Why a hand-rolled loop instead of autossh
    -----------------------------------------
    autossh is not available on Windows. This script is the equivalent: run ssh in the
    foreground of a loop, and when it exits, log why and start it again with exponential
    backoff. `ServerAliveInterval=30` + `ServerAliveCountMax=3` makes ssh itself notice a
    dead path within ~90 s, and `ExitOnForwardFailure=yes` makes it exit instead of
    lingering somewhere with no forward in place.

    Usage
    -----
        pwsh -File render-node.ps1                 # run in the foreground (Ctrl+C to stop)
        pwsh -File render-node.ps1 -NoService      # tunnel only, do not touch the service
        pwsh -File install-task.ps1                # install the logon Scheduled Task
#>

[CmdletBinding()]
param(
    # ── ssh / tunnel ────────────────────────────────────────────────────────────
    [string] $SshExe        = "$env:WINDIR\System32\OpenSSH\ssh.exe",
    [string] $SshKey        = "$env:USERPROFILE\.ssh\id_ed25519",
    [string] $SshTarget     = "root@www.liuliyue.com",
    [string] $LocalHost     = "127.0.0.1",
    [int]    $RemotePort    = 8760,
    [int]    $LocalPort     = 8760,

    # ── local render service ────────────────────────────────────────────────────
    [string] $ProjectDir    = "D:\DeepSeek Harness\workspace\osu-mania-render",
    [string] $PythonExe     = "",
    [switch] $NoService,

    # ── headless Chrome: the WebGL engine's render device ───────────────────────
    # Not optional. MANIA_ENGINE=webgl means every job drives this browser over CDP, so a
    # Chrome that is dead, closed by hand, or lost to a reboot takes rendering with it.
    [string] $ChromeExe     = "",
    [int]    $ChromePort    = 9222,
    [string] $ChromeProfile = "",
    [switch] $NoChrome,

    # ── PC-status reporter (blog homepage sidebar) ──────────────────────────────
    # Every $StatusEvery seconds this POSTs one small JSON document to the blog so
    # its homepage can show what this machine is doing. Push, not pull: when the PC
    # is off there is simply no heartbeat, which is unambiguous -- a server-side
    # poll could only ever see a timeout, and it would need a second tunnel port.
    #
    # The POST happens on EVERY due cycle, FlowTrak or no FlowTrak. What is in it
    # varies; whether it is sent does not. See the STATUS REPORTER section below.
    [string] $StatusUrl         = 'https://www.liuliyue.com/api/pc-status',
    # The shared secret lives in its own file (NOT in this script, NOT in the task
    # arguments) so it can be rotated without touching code. Never logged.
    [string] $StatusTokenFile   = '',
    [int]    $StatusEvery       = 60,
    [string] $FlowTrakHeartbeat = "$env:APPDATA\FlowTrak\tracker-heartbeat.json",
    # How old a heartbeat's own `savedAt` may be before this reporter stops
    # claiming a FlowTrak session. See "WHAT flowTrakRunning MEANS" below: 120 s
    # is ~24 write cycles (FlowTrak rewrites every 5 s), so no ordinary write or
    # delete+recreate gap can trip it, while a FlowTrak that has actually
    # stopped -- which leaves its last file behind, frozen -- is reported as not
    # running within about two minutes.
    [int]    $HeartbeatStaleSeconds = 120,
    # While there is no FlowTrak session the reporter keeps posting every
    # $StatusEvery seconds, but writes at most one *summary* line per this many
    # seconds -- a machine sitting without FlowTrak for hours must not warn on
    # every 15 s health tick.
    [int]    $StatusSummaryEvery = 300,
    [switch] $NoStatus,

    # ── housekeeping ────────────────────────────────────────────────────────────
    [int]    $BackoffMin    = 3,
    [int]    $BackoffMax    = 60,
    [int]    $HealthyAfter  = 120,   # a session this long resets the backoff
    [int]    $HealthEvery   = 15,    # seconds between health checks WHILE the tunnel is up
    [switch] $KillStaleTunnels,
    # NOT defaulted to (Join-Path $PSScriptRoot 'logs') here: under Windows PowerShell 5.1
    # -- which is what the Scheduled Task and the VBS launcher both start -- $PSScriptRoot
    # is EMPTY inside a param() default. It is only populated once the script body runs.
    # The default was therefore Join-Path '' 'logs', which threw
    #   "Cannot bind argument to parameter 'Path' because it is an empty string"
    # before a single line of the supervisor ran, and the script exited instantly with the
    # error going to a stderr nobody was reading (hidden launcher -> nowhere).
    # Left empty here and resolved in the body below.
    [string] $LogDir = ''
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $LogDir) { $LogDir = Join-Path $ScriptDir 'logs' }

# The Chrome profile has to be an explicit, dedicated directory: Chrome refuses a second
# instance that shares a profile with a running one (the new process just hands the URL to
# the old one and exits, leaving no CDP listener of its own), and the default profile is
# the user's own browser. Same value the hand-started Chrome on this machine used, so a
# browser that is already up is adopted rather than duplicated.
if (-not $ChromeProfile) { $ChromeProfile = Join-Path $ProjectDir 'cache\chrome-gpu-profile' }

# ─────────────────────────────────── paths / logs ───────────────────────────────

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ── single instance ─────────────────────────────────────────────────────────────
# The Scheduled Task uses MultipleInstances=IgnoreNew, but a manually started copy -- or
# a task that is mid-restart -- could overlap with it. Two supervisors would fight over
# the same remote forward, and the loser's ssh would fail ExitOnForwardFailure in a loop.
# A named mutex makes that impossible; it is released automatically if a supervisor dies.
$createdNew = $false
$script:Mutex = [System.Threading.Mutex]::new($true, 'Local\ManiaRenderNodeSupervisor', [ref]$createdNew)
if (-not $createdNew) {
    Write-Host 'another mania-render supervisor already holds the single-instance mutex -- exiting'
    exit 3
}

$SupervisorLog = Join-Path $LogDir 'supervisor.log'
$TunnelLog     = Join-Path $LogDir 'tunnel.log'
$SshErrFile    = Join-Path $LogDir 'ssh-last.err'
$SshOutFile    = Join-Path $LogDir 'ssh-last.out'
$ServiceOutLog = Join-Path $LogDir 'render-service.out.log'
$ServiceErrLog = Join-Path $LogDir 'render-service.err.log'
$ChromeOutLog  = Join-Path $LogDir 'chrome.out.log'
$ChromeErrLog  = Join-Path $LogDir 'chrome.err.log'
$PidFile       = Join-Path $LogDir 'render-node.pid'
$MaxLogBytes   = 5MB

function Write-Log {
    param([string] $Message, [ValidateSet('INFO','WARN','ERROR')] [string] $Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    try { Add-Content -LiteralPath $SupervisorLog -Value $line -Encoding utf8 } catch { }
}

function Rotate-Log {
    param([string] $Path)
    try {
        if ((Test-Path -LiteralPath $Path) -and (Get-Item -LiteralPath $Path).Length -gt $MaxLogBytes) {
            $old = "$Path.1"
            Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $Path -Destination $old -Force
        }
    } catch { }
}

# ─────────────────────────────── small helpers ──────────────────────────────────

function Test-TcpPort {
    param([string] $TargetHost = '127.0.0.1', [int] $Port = 8760, [int] $TimeoutMs = 1500)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch { return $false } finally { $client.Close() }
}

function Get-CpuCount { try { return [int]$env:NUMBER_OF_PROCESSORS } catch { return 0 } }

# Pick a Python that actually has the renderer's dependencies (Pillow + numpy).
function Resolve-Python {
    $candidates = @()
    if ($PythonExe) { $candidates += $PythonExe }
    $candidates += @(
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
        "D:\ComfyUI\ComfyUI_Windows_portable\python_standalone\python.exe",
        "C:\ComfyUI\ComfyUI_Windows_portable\python_standalone\python.exe"
    )
    foreach ($cand in $candidates) {
        if (-not (Test-Path -LiteralPath $cand)) { continue }
        & $cand -c "import PIL, numpy" 2>$null
        if ($LASTEXITCODE -eq 0) { return $cand }
        Write-Log "python candidate lacks Pillow/numpy, skipping: $cand" 'WARN'
    }
    return $null
}

# ──────────────────────────── headless Chrome (WebGL) ───────────────────────────

# The flags are the measured ones, not a guess. On this machine (RTX 5060 laptop):
#   --enable-gpu --use-angle=d3d11 --ignore-gpu-blocklist  ->  UNMASKED_RENDERER_WEBGL
#                                                              = ANGLE / NVIDIA RTX 5060 / D3D11
#   --use-angle=swiftshader                                ->  35 fps  (vs 259 fps on the GPU)
# so a Chrome that fell back to software would make every render ~7x slower while still
# "working". That is why the guard checks the flags and not merely that the port answers.
function Get-ChromeFlagList {
    # The profile is quoted EXPLICITLY. Start-Process -ArgumentList joins the array with
    # spaces and quotes nothing, and this profile lives under a path with a space in it
    # ("D:\DeepSeek Harness\..."). Unquoted, Chrome received three positional arguments
    # instead of one -- "--user-data-dir=D:\DeepSeek", "Harness\workspace\..." and
    # "...chrome-gpu-profile" -- and refused to start at all with
    #   ERROR:chrome\app\chrome_main.cc:204] Multiple targets are not supported in headless mode.
    # which is logged, by the supervisor, as "chrome did NOT answer ... within 60s".
    return @(
        '--headless=new'
        "--remote-debugging-port=$ChromePort"
        "--user-data-dir=`"$ChromeProfile`""
        '--enable-gpu'
        '--use-angle=d3d11'
        '--ignore-gpu-blocklist'
        '--enable-gpu-rasterization'
        '--no-first-run'
        '--no-default-browser-check'
        'about:blank'
    )
}

function Resolve-Chrome {
    $candidates = @()
    if ($ChromeExe) { $candidates += $ChromeExe }
    $candidates += @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path -LiteralPath $cand)) { return $cand }
    }
    return $null
}

# Every chrome.exe of OUR instance: the browser process plus its --type= children, matched
# on the dedicated profile directory (and, belt-and-braces, on the CDP port).
function Get-OurChromeProcesses {
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -and (
                    $_.CommandLine -match [regex]::Escape($ChromeProfile) -or
                    ($_.CommandLine -notmatch '--type=' -and
                     $_.CommandLine -match "--remote-debugging-port=$ChromePort(\s|`"|$)")
                )
            })
    } catch {
        Write-Log "could not enumerate chrome processes: $($_.Exception.Message)" 'WARN'
        return @()
    }
}

function Get-ChromeBrowserProcess {
    return @(Get-OurChromeProcesses | Where-Object { $_.CommandLine -notmatch '--type=' })
}

# Does that command line carry the GPU flags we need?
function Test-ChromeGpuFlags {
    param([string] $CommandLine)
    if (-not $CommandLine) { return $false }
    if ($CommandLine -match '--use-angle=swiftshader') { return $false }
    return (($CommandLine -match '--use-angle=d3d11') -and
            ($CommandLine -match '--enable-gpu') -and
            ($CommandLine -match '--ignore-gpu-blocklist'))
}

# Raw HTTP/1.1 GET of the CDP version endpoint -- returns the body, or '' when nothing
# answers. Deliberately not Invoke-WebRequest: this runs under the scheduled task's Windows
# PowerShell 5.1, where the cmdlet's defaults drag in the IE engine.
function Get-ChromeCdpVersion {
    param([int] $TimeoutMs = 2000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', $ChromePort, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return '' }
        $client.EndConnect($iar)
        $stream = $client.GetStream()
        $stream.ReadTimeout = $TimeoutMs
        $stream.WriteTimeout = $TimeoutMs
        $req = [System.Text.Encoding]::ASCII.GetBytes(
            "GET /json/version HTTP/1.1`r`nHost: 127.0.0.1:$ChromePort`r`nConnection: close`r`n`r`n")
        $stream.Write($req, 0, $req.Length)
        $buf = New-Object byte[] 8192
        $sb = New-Object System.Text.StringBuilder
        $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
        while ((Get-Date) -lt $deadline) {
            $n = 0
            try { $n = $stream.Read($buf, 0, $buf.Length) } catch { break }
            if ($n -le 0) { break }
            [void]$sb.Append([System.Text.Encoding]::ASCII.GetString($buf, 0, $n))
            if ($sb.ToString() -match '"Browser"') { break }
        }
        return $sb.ToString()
    } catch {
        return ''
    } finally { $client.Close() }
}

function Test-ChromeUp {
    $body = Get-ChromeCdpVersion
    return ($body -match '"Browser"')
}

function Wait-ForChrome {
    param([int] $TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ChromeUp) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Stop-OurChrome {
    $victims = @(Get-OurChromeProcesses)
    foreach ($p in $victims) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
    }
    if ($victims.Count) { Start-Sleep -Seconds 2 }
    return $victims.Count
}

function Start-Chrome {
    param([string] $Exe)
    $flags = Get-ChromeFlagList
    Rotate-Log $ChromeOutLog
    Rotate-Log $ChromeErrLog
    # -WindowStyle Hidden for the same reason the render service uses it: this is started
    # from a hidden scheduled task, and a stray console window would appear on the desktop.
    $p = Start-Process -FilePath $Exe -ArgumentList $flags -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $ChromeOutLog -RedirectStandardError $ChromeErrLog
    Write-Log "chrome started pid=$($p.Id) cdp=127.0.0.1:$ChromePort profile=$ChromeProfile"
    Write-Log "  flags: $($flags -join ' ')"
    return $p
}

# ──────────────────────────── killing tunnels left by a previous run ────────────────

function Stop-StaleTunnels {
    # Only ssh processes that forward OUR remote port -- the user runs other tunnels
    # (-L 6185, -L 6099, ...) and those must not be touched.
    $mine = @()
    try {
        $mine = @(Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -match "-R\s+$RemotePort`:" })
    } catch {
        Write-Log "could not enumerate ssh processes: $($_.Exception.Message)" 'WARN'
        return
    }
    foreach ($p in $mine) {
        Write-Log "stopping stale tunnel pid=$($p.ProcessId)" 'WARN'
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
    }
    if ($mine.Count) { Start-Sleep -Seconds 2 }
}

# ─────────────────────────────── the render service ─────────────────────────────

function Start-RenderService {
    param([string] $Python)
    # MANIA_ENGINE=webgl: the page renderer, driven in headless Chrome over CDP, is the
    # engine the visual conformance work was checked against and the picture a human sees
    # in the browser. It needs Chrome on 127.0.0.1:9222, which this script now supervises
    # (see the Chrome section above); 'python' stays available per-request as a fallback.
    $env:MANIA_ENGINE       = 'webgl'
    $env:MANIA_HOST         = $LocalHost
    $env:MANIA_PORT         = "$LocalPort"
    $env:PYTHONUNBUFFERED   = '1'
    Rotate-Log $ServiceOutLog
    Rotate-Log $ServiceErrLog
    $p = Start-Process -FilePath $Python `
        -ArgumentList @('-m', 'mania_render', '--web', '--port', "$LocalPort") `
        -WorkingDirectory $ProjectDir -WindowStyle Hidden `
        -RedirectStandardOutput $ServiceOutLog -RedirectStandardError $ServiceErrLog `
        -PassThru
    Write-Log "render service started pid=$($p.Id) ($Python) engine=webgl workers<=$([Math]::Max(2,[Math]::Min(16,(Get-CpuCount)-2)))"
    return $p
}

function Wait-ForService {
    param([int] $TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -TargetHost $LocalHost -Port $LocalPort) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# ── the two checks the tunnel loop runs periodically ────────────────────────────
# They live in functions because they have to run BOTH before a tunnel attempt and every
# $HealthEvery seconds while one is up. The old shape called them once and then sat in
# $proc.WaitForExit() for as long as the tunnel held -- so a render service or a Chrome
# that died mid-session stayed dead until the tunnel happened to drop. That is precisely
# the failure this script exists to prevent.

function Ensure-RenderService {
    if ($NoService) { return }
    if (Test-TcpPort -TargetHost $LocalHost -Port $LocalPort) { return }
    if (-not $python) { return }
    Write-Log "render service not listening on ${LocalHost}:${LocalPort} -- starting it"
    try { Start-RenderService -Python $python | Out-Null } catch {
        Write-Log "failed to start render service: $($_.Exception.Message)" 'ERROR'
    }
    if (Wait-ForService 90) { Write-Log "render service is up on ${LocalHost}:${LocalPort}" }
    else { Write-Log "render service did NOT come up within 90s" 'ERROR' }
}

function Ensure-Chrome {
    if ($NoChrome) { return }
    # Checked every pass, not only at start: Chrome is a normal desktop application that
    # anything on this machine can close, and a reboot leaves nothing behind. Three cases,
    # in the order they have to be told apart:
    #   a) our browser holds the port with the GPU flags  -> nothing to do (the common case)
    #   b) something answers on the port WITHOUT the flags -> it is not ours to trust;
    #      a swiftshader Chrome renders ~7x slower while looking perfectly healthy
    #   c) nothing answers -> start one (clearing a hung browser first, so the relaunch does
    #      not inherit a locked profile)
    $browsers = @(Get-ChromeBrowserProcess)
    $badFlags = @($browsers | Where-Object { -not (Test-ChromeGpuFlags $_.CommandLine) })
    if ($badFlags.Count) {
        foreach ($p in $badFlags) {
            Write-Log "chrome pid=$($p.ProcessId) on :$ChromePort is missing the GPU flags -- replacing it" 'WARN'
            Write-Log "  its command line: $($p.CommandLine)" 'WARN'
        }
        [void](Stop-OurChrome)
    } elseif (-not (Test-ChromeUp)) {
        if ($browsers.Count) {
            Write-Log "chrome pid=$($browsers[0].ProcessId) is not answering on :$ChromePort -- restarting it" 'WARN'
            [void](Stop-OurChrome)
        }
    }

    if (-not (Test-ChromeUp)) {
        $chrome = Resolve-Chrome
        if (-not $chrome) {
            Write-Log 'no chrome.exe found -- the WebGL engine can NOT render' 'ERROR'
        } else {
            Write-Log "no Chrome answering on 127.0.0.1:$ChromePort -- starting $chrome"
            try { Start-Chrome -Exe $chrome | Out-Null } catch {
                Write-Log "failed to start chrome: $($_.Exception.Message)" 'ERROR'
            }
            if (Wait-ForChrome 60) {
                $ver = Get-ChromeCdpVersion
                $browser = if ($ver -match '"Browser"\s*:\s*"([^"]+)"') { $Matches[1] } else { '?' }
                Write-Log "chrome is up on 127.0.0.1:$ChromePort ($browser)"
            } else {
                Write-Log "chrome did NOT answer on 127.0.0.1:$ChromePort within 60s" 'ERROR'
            }
        }
    }
}

# ───────────────────────────── PC-status reporter ───────────────────────────────
# Feeds the "主机状态" panel in the blog's homepage sidebar
# (https://www.liuliyue.com/ , POST /api/pc-status).
#
# TWO INDEPENDENT FACTS, AND WHY CONFLATING THEM WAS A BUG
# -------------------------------------------------------
# The panel can say "offline" for two completely different reasons, and before
# 2026-09-30 this reporter conflated them:
#
#   1. this PC is off            -> decided SERVER-side, from whether a POST has
#                                   arrived within the staleness threshold. That
#                                   is the only thing that means 已关机.
#   2. FlowTrak is not running   -> decided HERE, and it says NOTHING about
#                                   whether the PC is up.
#
# The old build skipped the POST entirely whenever FlowTrak's heartbeat could
# not be read, so fact (2) was published as fact (1).  Measured, after the
# 10:15 reboot on 2026-09-30: the machine was up, the render service answered,
# the tunnel was up -- and the public panel read 已关机 / om 渲染 不可用 for the
# whole ~30 minutes FlowTrak happened not to be running:
#   10:44:40 [WARN] ... no readable heartbeat ... (108 consecutive misses) --
#                   nothing posted (the blog will age this machine out)
#   10:45:12 [INFO] ... heartbeat posted (HTTP 200 via direct, ...)
# It "recovered" by itself the moment FlowTrak started, which is what made this
# look like a PC problem rather than a reporter problem.
#
# WHAT IS REPORTED, AND WHY IT IS A PUSH
# --------------------------------------
# FlowTrak (this machine's foreground-app tracker) rewrites
#   %APPDATA%\FlowTrak\tracker-heartbeat.json
# every 5-10 s and exposes NO HTTP interface at all. So the data is pushed here,
# on the same 60 s heartbeat the user asked for, rather than pulled by the
# server: when this PC is off there is simply no POST, which the blog reads as
# "已关机" without ambiguity. A server-side pull could only ever observe a
# timeout -- indistinguishable from a network blip -- and it would need a second
# reverse-tunnel port on a box that is deliberately kept to one (8760).
#
# The POST goes to the public HTTPS origin, NOT through the tunnel: the tunnel
# forwards 8760 only, and adding a forward for 8090 would be exactly the extra
# port this design avoids.
#
# WHAT flowTrakRunning MEANS  (the field the blog renders)
# --------------------------------------------------------
# A FlowTrak session exists -- and flowTrakRunning is true -- only when BOTH:
#   a) FlowTrak.exe is present in the process list (and is not *known* absent:
#      if the process list itself cannot be read the heartbeat alone decides,
#      rather than a failed enumeration being published as "not running"), and
#   b) a heartbeat whose `savedAt` is at most $HeartbeatStaleSeconds old is in
#      hand -- read now, or (when the read failed) the last good one, while it
#      is still inside that window.
# Otherwise the POST carries flowTrakRunning = false, empty app fields and
# savedAt = 0.
#
# WHAT IS NOT REPORTED
# --------------------
# The window title travels (the blog decides whether to publish it, and NEVER
# for a browser -- see app/pcstatus.py), but keyboardCount/mouseCount are
# behavioural data and are accepted server-side only to be stored unrendered.
# The token is never logged, printed, or put on a command line.
#
# FAILURE POLICY
# --------------
# Every path here is wrapped: this reporter must never be able to take down the
# three guards above it. A failed POST is a WARN line and nothing else.

# PS 5.1 (what the Scheduled Task actually runs) defaults to TLS 1.0, which
# nginx refuses -- without this every POST would fail the handshake.
function Enable-StatusTls {
    try {
        $current = [Net.ServicePointManager]::SecurityProtocol
        if (($current -band [Net.SecurityProtocolType]::Tls12) -eq 0) {
            [Net.ServicePointManager]::SecurityProtocol = $current -bor [Net.SecurityProtocolType]::Tls12
        }
    } catch { }
}

# One POST, over one of the two routes out of this machine.
#
# WHY THERE ARE TWO (measured 2026-09-29): this machine has a system HTTP proxy
# configured (WinINet: ProxyEnable=1, 127.0.0.1:7890) and Windows PowerShell
# 5.1's Invoke-WebRequest picks it up automatically, because it inherits the
# IE/WinINet default proxy.  Through it the POST to the blog took 6.8 s when it
# worked at all, and twice it timed out outright (30 s, no response) -- the
# blog is a public host on a direct route, and curl.exe to the same URL
# answers in 0.22 s.  So the first attempt pins the request to a DIRECT
# connection (DefaultWebProxy with no address = no proxy), and only if that
# fails does it fall back to the system default, in case this machine ever ends
# up somewhere the proxy is the only way out.
function Invoke-StatusPost {
    param([byte[]] $Body, [int] $TimeoutSec = 8)
    $savedProxy = [System.Net.WebRequest]::DefaultWebProxy
    try {
        [System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy
        $r = Invoke-WebRequest -Uri $StatusUrl -Method POST `
            -Headers @{ 'X-Status-Token' = $script:StatusToken } `
            -ContentType 'application/json; charset=utf-8' `
            -Body $Body -UseBasicParsing -TimeoutSec $TimeoutSec
        return @{ Response = $r; Route = 'direct' }
    } catch {
        $directError = $_.Exception.Message
        try {
            [System.Net.WebRequest]::DefaultWebProxy = $savedProxy
            $r = Invoke-WebRequest -Uri $StatusUrl -Method POST `
                -Headers @{ 'X-Status-Token' = $script:StatusToken } `
                -ContentType 'application/json; charset=utf-8' `
                -Body $Body -UseBasicParsing -TimeoutSec 12
            return @{ Response = $r; Route = 'system-proxy' }
        } catch {
            throw "direct: $directError | via system proxy: $($_.Exception.Message)"
        }
    } finally {
        [System.Net.WebRequest]::DefaultWebProxy = $savedProxy
    }
}

# StrictMode 2.0 makes a reference to a MISSING property an error, and the
# heartbeat is written by a third-party app whose schema we do not control.
function Get-JsonField {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    try {
        if (@($Object.PSObject.Properties.Name) -contains $Name) { return $Object.$Name }
    } catch { }
    return $Default
}

function ConvertTo-SafeLong {
    param($Value, [long] $Min = 0, [long] $Max = [long]::MaxValue, [long] $Default = 0)
    try {
        if ($null -eq $Value -or "$Value" -eq '') { return $Default }
        $n = [long]$Value
        if ($n -lt $Min) { return $Min }
        if ($n -gt $Max) { return $Max }
        return $n
    } catch { return $Default }
}

function ConvertTo-SafeBool {
    param($Value, [bool] $Default = $false)
    try { return [bool]$Value } catch { return $Default }
}

function Get-StatusToken {
    if (-not (Test-Path -LiteralPath $StatusTokenFile)) { return '' }
    try {
        $raw = Get-Content -LiteralPath $StatusTokenFile -Raw -ErrorAction Stop
        if (-not $raw) { return '' }
        # Trailing newline / a stray BOM from however the file was written.
        return (($raw -replace '\s', '').Trim([char]0xFEFF))
    } catch {
        Write-Log "status reporter: could not read the token file: $($_.Exception.Message)" 'WARN'
        return ''
    }
}

# Is FlowTrak.exe running?
#
# Three-valued ON PURPOSE.  $true / $false are answers; $null means "this
# machine would not tell us" (the process list could not be enumerated at all).
# It matters because the CALLER ANDs this with the heartbeat: a failed
# enumeration must not be published as "FlowTrak is not running", which is a
# public claim about the user's desktop, so $null there simply leaves the
# decision to the heartbeat.
#
# Enumerating and filtering, rather than `Get-Process -Name FlowTrak`, because
# that form raises the SAME non-terminating error for "no such process" as for a
# real enumeration failure -- the two would be indistinguishable.
function Get-FlowTrakProcessState {
    try {
        $all = @(Get-Process -ErrorAction Stop)
        return (@($all | Where-Object { $_.ProcessName -eq 'FlowTrak' }).Count -gt 0)
    } catch { return $null }
}

# How old a heartbeat's own `savedAt` is, in seconds; $null when the value is
# missing or unusable.
#
# `savedAt` is an epoch stamp in MILLIseconds (measured on this machine's file:
# 1790737690164 at 2026-09-30 11:08 +08:00).  The whole subtraction is done in
# UTC on purpose: `Get-Date` is LOCAL, so comparing an epoch stamp against it
# would be out by the machine's UTC offset -- 8 h here -- and would declare
# every heartbeat stale, i.e. rebuild the exact bug this file just fixed.
function Get-HeartbeatAgeSeconds {
    param($Heartbeat)
    if ($null -eq $Heartbeat) { return $null }
    $savedMs = ConvertTo-SafeLong (Get-JsonField $Heartbeat 'savedAt' 0) 0 ([long]::MaxValue) 0
    if ($savedMs -le 0) { return $null }
    $epoch = [datetime]::SpecifyKind([datetime]'1970-01-01', [System.DateTimeKind]::Utc)
    $nowMs = [long](([datetime]::UtcNow - $epoch).TotalMilliseconds)
    return (($nowMs - $savedMs) / 1000.0)
}

# One read of the heartbeat file, or $null when it cannot be read/parsed.
function Read-FlowTrakHeartbeatOnce {
    if (-not (Test-Path -LiteralPath $FlowTrakHeartbeat)) { return $null }
    try {
        $raw = Get-Content -LiteralPath $FlowTrakHeartbeat -Raw -ErrorAction Stop
        if (-not $raw -or -not $raw.Trim()) { return $null }
        return ($raw | ConvertFrom-Json -ErrorAction Stop)
    } catch { return $null }
}

# ... and the retrying wrapper the reporter actually uses.
#
# WHY THIS RETRIES (all numbers measured on this machine, 2026-09-29)
# ------------------------------------------------------------------
# FlowTrak writes the file in place every ~5 s AND deletes + recreates it every
# ~45 s.  During that recreate the path simply does not exist:
#     sampling every 50 ms for 90 s -> 274 of 1433 samples missing (19.1%),
#     in 2 episodes of 113 and 161 samples, i.e. gaps of 5.6 s and 8.0 s.
# (A second run at 100 ms spacing saw 133/499 -- the same phenomenon, sampled
#  differently.)  So a single read misses about one time in five, and three
# attempts 400 ms apart ride out only the short end of the gap: measured
# miss rate falls from 12.5% (one shot) to 10% (this wrapper) over 40 trials.
#
# The real defence is therefore in Send-PcStatus: a read that fails is served
# from the last good read while that is still fresh, so the POST goes out
# correctly either way, and a genuine absence is what a sustained failure means.
# This wrapper is the cheap first line; the cache is the second.
function Get-FlowTrakHeartbeat {
    param([int] $Attempts = 3, [int] $DelayMs = 400)
    for ($i = 1; $i -le $Attempts; $i++) {
        $hb = Read-FlowTrakHeartbeatOnce
        if ($null -ne $hb) { return $hb }
        if ($i -lt $Attempts) { Start-Sleep -Milliseconds $DelayMs }
    }
    return $null
}

# ── now playing (Windows SMTC) ───────────────────────────────────────────────
# FlowTrak's own heartbeat carries NO track information -- its fields are
# appId / processName / windowTitle / durationMs / counters / savedAt and
# nothing else -- and its SQLite file is not readable (the header is not a
# SQLite one), so the music cannot be relayed from FlowTrak at all.
#
# What CAN be read is the same OS-level source FlowTrak itself uses to show a
# song: the Global System Media Transport Controls session that whatever player
# is running (Spotify, foobar2000, a browser tab, ...) registers with Windows.
# That is what this reads, independently of FlowTrak: music can be playing while
# FlowTrak is closed, and the panel should still say so.
#
# Everything here is best-effort.  A machine with no media session, a player
# that never registers with SMTC, or a Windows build without the API must leave
# the heartbeat POST exactly as it was -- never fail it.  Type resolution is
# cached because that is the slow part, and a failure is logged once rather than
# every 60 s.
$script:NowPlayingFailures = 0
$script:NowPlayingLogged = $false
$script:SmtsTypes = $null

# The machine's boot time, read once per run (see Get-BootTime).  Initialised
# here because the script runs under `Set-StrictMode -Version Latest`: merely
# READING an unset script-scope variable throws, and a throw inside the status
# reporter fails the whole heartbeat POST -- which is how a missing cache slot
# turned into "the PC looks offline" for two minutes.
$script:BootTime = $null

function Wait-WinRtOperation {
    param($Operation, [type] $ResultType)
    $method = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait(-1) | Out-Null
    $task.Result
}

# A hashtable of Title/Artist/Album/Status/Source, or $null when nothing is
# playing (or the whole facility is unavailable on this machine).
function Get-NowPlaying {
    try {
        if ($null -eq $script:SmtsTypes) {
            Add-Type -AssemblyName System.Runtime.WindowsRuntime
            $script:SmtsTypes = @{
                Manager = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
                Props   = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType = WindowsRuntime]
            }
        }
        $managerType = $script:SmtsTypes.Manager
        $propsType = $script:SmtsTypes.Props
        $manager = Wait-WinRtOperation ($managerType::RequestAsync()) $managerType
        if ($null -eq $manager) { return $null }
        $session = $manager.GetCurrentSession()
        if ($null -eq $session) { return $null }

        $status = ''
        try { $status = [string]$session.GetPlaybackInfo().PlaybackStatus } catch { }

        $title = ''; $artist = ''; $album = ''
        try {
            $props = Wait-WinRtOperation ($session.TryGetMediaPropertiesAsync()) $propsType
            if ($null -ne $props) {
                $title = [string]$props.Title
                $artist = [string]$props.Artist
                $album = [string]$props.AlbumTitle
            }
        } catch { }

        # A session with no title is not worth publishing.
        if ([string]::IsNullOrWhiteSpace($title)) { return $null }

        # Clamped to the blog's own field limits, exactly like the app fields:
        # an over-long value would 422 the whole report instead of being cut.
        if ($title.Length -gt 300) { $title = $title.Substring(0, 300) }
        if ($artist.Length -gt 300) { $artist = $artist.Substring(0, 300) }
        if ($album.Length -gt 300) { $album = $album.Substring(0, 300) }
        $source = [string]$session.SourceAppUserModelId
        if ($source.Length -gt 120) { $source = $source.Substring(0, 120) }
        if ($status.Length -gt 32) { $status = $status.Substring(0, 32) }

        $script:NowPlayingFailures = 0
        return @{ Title = $title; Artist = $artist; Album = $album
                  Status = $status; Source = $source }
    } catch {
        $script:NowPlayingFailures++
        if (-not $script:NowPlayingLogged) {
            $script:NowPlayingLogged = $true
            Write-Log ("now playing: SMTC unavailable ($($_.Exception.Message)) -- " +
                       "heartbeats continue without track information") 'WARN'
        }
        return $null
    }
}

# What is loaded in osu! right now, straight off its window title:
#
#     osu! - Kurokotei - Scattered Faith [Catastrophic Trust]
#     \___/  \______/   \_____________/  \________________/
#     product  artist        title           difficulty
#
# While a map is loaded osu! puts the beatmap in its own window title, so this
# needs no plugin, no memory reading and no API credentials -- just the window
# of the running process.  With no map loaded the title is only the product name
# ("osu!"), which parses to nothing and reports nothing.
#
# The artist/title split takes the FIRST " - " (osu!'s own separator is
# "{artist} - {title}"), so an artist whose name contains " - " lands in the
# title instead.  That is a cosmetic miss on a rare name, and deliberately not
# guessed around: any other rule would mangle far more maps than it fixed.
function Get-OsuBeatmap {
    try {
        $procs = @(Get-Process -Name 'osu!' -ErrorAction SilentlyContinue)
        if ($procs.Count -eq 0) { return $null }

        foreach ($proc in $procs) {
            $raw = ''
            try { $raw = [string]$proc.MainWindowTitle } catch { }
            if ([string]::IsNullOrWhiteSpace($raw)) { continue }

            # "osu!" / "osu!lazer" followed by the beatmap; anything else is not
            # a loaded map (the main menu, or another window that happens to
            # start with the product name).
            $m = [regex]::Match($raw, '^osu!(?:lazer)?\s+-\s+(?<rest>.+)$')
            if (-not $m.Success) { continue }
            $rest = $m.Groups['rest'].Value.Trim()

            $title = $rest
            $diff = ''
            $dm = [regex]::Match($rest, '^(?<t>.*?)\s*\[(?<d>[^\]]+)\]\s*$')
            if ($dm.Success) {
                $title = $dm.Groups['t'].Value.Trim()
                $diff = $dm.Groups['d'].Value.Trim()
            }
            $artist = ''
            $am = [regex]::Match($title, '^(?<a>.+?)\s+-\s+(?<t>.+)$')
            if ($am.Success) {
                $artist = $am.Groups['a'].Value.Trim()
                $title = $am.Groups['t'].Value.Trim()
            }
            if ([string]::IsNullOrWhiteSpace($title)) { continue }

            # Clamped to the blog's field limits: an over-long value would 422
            # the whole report instead of being cut.
            if ($artist.Length -gt 200) { $artist = $artist.Substring(0, 200) }
            if ($title.Length -gt 200) { $title = $title.Substring(0, 200) }
            if ($diff.Length -gt 120) { $diff = $diff.Substring(0, 120) }

            return @{ Artist = $artist; Title = $title; Difficulty = $diff }
        }
        return $null
    } catch {
        # A missing process or a denied window handle is not worth a WARN every
        # tick; the beatmap line simply stays empty.
        return $null
    }
}

# Epoch seconds of this machine's last boot.
#
# This is what makes "the PC just started" a fact rather than a guess.  Watching
# for the heartbeat to come back instead would fire on a tunnel blip, a wifi
# drop, or a wake from sleep -- none of which are a boot -- and would only miss
# nothing by accident.  Read ONCE per run and cached: the boot time cannot change
# while this script is alive, and the CIM query is not free.
function Get-BootTime {
    if ($null -ne $script:BootTime) { return $script:BootTime }
    try {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
        # LastBootUpTime comes back as a local DateTime; converting through
        # DateTimeOffset applies this machine's offset, so the epoch stays correct
        # across a daylight-saving change.
        $dto = [DateTimeOffset]$os.LastBootUpTime
        $script:BootTime = [int]$dto.ToUnixTimeSeconds()
    } catch {
        # Not fatal: the heartbeat still carries everything else.  0 means
        # "unknown", and the blog treats 0 as "no boot information".
        $script:BootTime = 0
    }
    return $script:BootTime
}

function Send-PcStatus {    param([switch] $Force)

    if ($NoStatus) { return }
    if (-not $script:StatusToken) { return }

    $nowStamp = Get-Date
    if (-not $Force -and ($nowStamp - $script:StatusLastAt).TotalSeconds -lt $StatusEvery) { return }
    # Stamped BEFORE the attempt: a slow or hanging POST must not let the next
    # health tick queue another one behind it.
    $script:StatusLastAt = $nowStamp

    try {
        # ── 1. is FlowTrak running?  (see "WHAT flowTrakRunning MEANS" above) ───
        $procState = Get-FlowTrakProcessState      # $true / $false / $null = unknown

        # ── 2. a heartbeat to describe it with ─────────────────────────────────
        # (a) read now -- 3 attempts, because the file is deleted and recreated
        #     every ~45 s and a single read lands in that gap about one time in
        #     five;
        $hb  = Get-FlowTrakHeartbeat
        $age = Get-HeartbeatAgeSeconds $hb
        if ($null -ne $age -and $age -le $HeartbeatStaleSeconds) {
            $script:StatusHbCache = $hb
            $script:StatusMisses  = 0
        } else {
            # (b) that failed, or came back frozen.  Fall back to the last good
            #     read WHILE IT IS STILL INSIDE THE WINDOW -- without this a read
            #     landing in the recreate gap would publish "FlowTrak 未运行" for
            #     a whole 60 s cycle, and the panel would flap about once every
            #     ten minutes for no reason at all.  A frozen file (FlowTrak
            #     killed, its last write left behind) ages out of the window and
            #     does NOT fall back, which is what makes a stopped FlowTrak
            #     eventually visible.
            $script:StatusMisses++
            $cacheAge = Get-HeartbeatAgeSeconds $script:StatusHbCache
            if ($null -ne $cacheAge -and $cacheAge -le $HeartbeatStaleSeconds) {
                $hb  = $script:StatusHbCache
                $age = $cacheAge
            } else {
                $hb  = $null
                $age = $null
            }
        }

        # A session exists only when BOTH inputs agree.  $null (the process list
        # could not be read) does not veto a fresh heartbeat; a definite "not in
        # the list" does -- which is what makes killing FlowTrak visible at once
        # instead of only after $HeartbeatStaleSeconds.
        $running = ($null -ne $hb) -and ($procState -ne $false)

        if ($running) {
            $procName = [string](Get-JsonField $hb 'processName' '')
            $winTitle = [string](Get-JsonField $hb 'windowTitle' '')
            # Clamped to the blog's own field limits: an over-long title would
            # otherwise 422 the entire report instead of just being cut.
            if ($procName.Length -gt 120) { $procName = $procName.Substring(0, 120) }
            if ($winTitle.Length -gt 300) { $winTitle = $winTitle.Substring(0, 300) }
            $durationMs = ConvertTo-SafeLong (Get-JsonField $hb 'durationMs' 0) 0 315576000000 0
            $isIdle     = ConvertTo-SafeBool (Get-JsonField $hb 'isIdle' $false) $false
            $savedAt    = ConvertTo-SafeLong (Get-JsonField $hb 'savedAt' 0) 0 ([long]::MaxValue) 0
            $keyboard   = ConvertTo-SafeLong (Get-JsonField $hb 'keyboardCount' 0) 0 100000000 0
            $mouse      = ConvertTo-SafeLong (Get-JsonField $hb 'mouseCount' 0) 0 100000000 0
        } else {
            # NO FlowTrak session.  Nothing is invented: the app fields go out
            # empty and -- the part that matters -- `savedAt` goes out as 0
            # rather than whatever stamp the last file happened to carry.  A
            # stale `savedAt` from here is precisely what let the blog age this
            # machine out while it was up, so this reporter never puts one on the
            # wire.  Whether the PC is up is the POST's ARRIVAL, and that is now
            # unconditional.
            $procName   = ''
            $winTitle   = ''
            $durationMs = 0
            $isIdle     = $false
            $savedAt    = 0
            $keyboard   = 0
            $mouse      = 0
        }

        # ── 3. what is playing ────────────────────────────────────────────────
        # Deliberately NOT inside the `if ($running)` branch above: the media
        # session belongs to the PC, not to FlowTrak, so it is reported even
        # while FlowTrak is closed (and the panel shows it in that state too).
        $nowPlaying = Get-NowPlaying
        $mediaTitle = ''; $mediaArtist = ''; $mediaAlbum = ''
        $mediaStatus = ''; $mediaSource = ''
        if ($null -ne $nowPlaying) {
            $mediaTitle  = $nowPlaying.Title
            $mediaArtist = $nowPlaying.Artist
            $mediaAlbum  = $nowPlaying.Album
            $mediaStatus = $nowPlaying.Status
            $mediaSource = $nowPlaying.Source
        }

        # ── 3b. what is loaded in osu! ────────────────────────────────────────
        # Same reasoning as the media session above: this belongs to the PC, so
        # it is reported whether or not FlowTrak is running.  It is the BEATMAP,
        # not a page title, so the blog's browser rule does not apply to it.
        $osu = Get-OsuBeatmap
        $osuTitle = ''; $osuArtist = ''; $osuDiff = ''
        if ($null -ne $osu) {
            $osuTitle  = $osu.Title
            $osuArtist = $osu.Artist
            $osuDiff   = $osu.Difficulty
        }

        # ── 3c. when this machine last started ────────────────────────────────
        # Read once per run (see Get-BootTime).  A CHANGE here between two
        # heartbeats is the only honest evidence of a boot; the blog hands it to
        # the QQ bot, which greets the owner.
        $bootTime = Get-BootTime

        $payload = [ordered]@{
            # Straight out of the heartbeat file (empty when there is none).
            processName     = $procName
            windowTitle     = $winTitle
            durationMs      = $durationMs
            isIdle          = $isIdle
            savedAt         = $savedAt
            # Observed here: does the render service actually answer its port?
            # Measured on EVERY post, FlowTrak or not -- this is the field that
            # keeps 可用 on the panel right through a FlowTrak outage.
            renderAvailable = [bool](Test-TcpPort -TargetHost $LocalHost -Port $LocalPort)
            flowTrakRunning = [bool]$running
            # The process-list answer ON ITS OWN: was FlowTrak.exe seen?  $null
            # means the enumeration failed and we do not know.
            #
            # Published separately because `flowTrakRunning` means "a session
            # exists", which needs a FRESH heartbeat too -- and FlowTrak's
            # heartbeat does lapse while the process is very much alive
            # (measured: frozen for 28 minutes on 2026-09-30 20:59-21:27, and
            # for about a minute twice that evening).  Folding the two together
            # made the panel announce "FlowTrak 未运行" about a FlowTrak that was
            # running and had just been seen in the process list, which is a
            # claim the reporter knows to be false.
            flowTrakProcess = $procState
            keyboardCount   = $keyboard
            mouseCount      = $mouse
            # Read from the Windows media session (see Get-NowPlaying).  Empty
            # when nothing is playing; the blog applies its own privacy rules
            # before any of this reaches a template.
            mediaTitle      = $mediaTitle
            mediaArtist     = $mediaArtist
            mediaAlbum      = $mediaAlbum
            mediaStatus     = $mediaStatus
            mediaSource     = $mediaSource
            # The beatmap osu! has loaded, parsed from its window title (see
            # Get-OsuBeatmap).  Empty when osu! is closed or sitting on a menu.
            osuTitle        = $osuTitle
            osuArtist       = $osuArtist
            osuDifficulty   = $osuDiff
            # Epoch seconds of the last boot (0 = unknown).  Not shown on the
            # panel: a record of when the owner starts their day belongs to the
            # bot, not to a public page -- the blog only serves it on the
            # loopback-only route the bot reads.
            bootTime        = $bootTime
        }

        $json = $payload | ConvertTo-Json -Compress
        Enable-StatusTls
        $attempt = Invoke-StatusPost -Body ([System.Text.Encoding]::UTF8.GetBytes($json))
        $response = $attempt.Response
        $code = $null
        try { $code = [int]$response.StatusCode } catch { }

        # ── 3. logging: one line per POST, one line per STATE CHANGE, and while
        #       FlowTrak is absent one summary every $StatusSummaryEvery seconds.
        #       Never one WARN per 15 s tick.
        # The app name is fine in the log; the window title is NOT (a browser
        # title is the user's page content, and this log is on disk).
        $shownApp = if ($procName) { $procName } else { '-' }
        Write-Log ("status reporter: heartbeat posted (HTTP $code via " + $attempt.Route +
            ", app=" + $shownApp + ", flowtrak=" + $payload.flowTrakRunning +
            ", render=" + $payload.renderAvailable + ")")

        if ($script:FlowTrakState -ne $running) {
            if ($running) {
                $hbText = if ($null -ne $age) { "heartbeat $([int]$age)s old" } else { 'heartbeat fresh' }
                Write-Log "status reporter: FlowTrak is running ($hbText, app=$shownApp) -- the panel shows it"
            } else {
                $why = @()
                if ($null -eq $hb) {
                    $why += "no heartbeat newer than ${HeartbeatStaleSeconds}s ($($script:StatusMisses) consecutive unreadable or frozen reads)"
                }
                if ($procState -eq $false) { $why += 'FlowTrak.exe is not in the process list' }
                Write-Log ("status reporter: FlowTrak is NOT running (" + ($why -join '; ') +
                    ") -- posting flowTrakRunning=false; this PC is still up, so the panel stays 在线 with 当前应用 FlowTrak 未运行") 'WARN'
            }
            $script:FlowTrakState   = $running
            $script:StatusSummaryAt = $nowStamp
            $script:StatusAbsent    = 0
        } elseif (-not $running) {
            # Still absent: keep the log honest but quiet.
            $script:StatusAbsent++
            if (($nowStamp - $script:StatusSummaryAt).TotalSeconds -ge $StatusSummaryEvery) {
                $forSec = [int](($nowStamp - $script:StatusSummaryAt).TotalSeconds)
                Write-Log "status reporter: still no FlowTrak session (${forSec}s, $($script:StatusAbsent) posts with flowTrakRunning=false) -- still posting every ${StatusEvery}s, the panel is 在线" 'WARN'
                $script:StatusSummaryAt = $nowStamp
            }
        }
    } catch {
        $code = ''
        try {
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $code = ' HTTP ' + [int]$_.Exception.Response.StatusCode
            }
        } catch { }
        Write-Log "status reporter: POST failed$code ($($_.Exception.Message))" 'WARN'
    }
}

# ─────────────────────────────────── main loop ──────────────────────────────────

Write-Log '================ mania-render node supervisor starting ================'
Write-Log "project=$ProjectDir  local=${LocalHost}:${LocalPort}  remote=:${RemotePort} via $SshTarget"
Write-Log "chrome=127.0.0.1:$ChromePort profile=$ChromeProfile exe=$(Resolve-Chrome)"

if (-not (Test-Path -LiteralPath $SshExe))  { Write-Log "ssh not found: $SshExe" 'ERROR';  exit 2 }
if (-not (Test-Path -LiteralPath $SshKey))  { Write-Log "ssh key not found: $SshKey" 'ERROR'; exit 2 }

if ($KillStaleTunnels) { Stop-StaleTunnels }

# ── the PC-status reporter's startup state ──────────────────────────────────────
# Resolved here rather than in param() for the same reason $LogDir is: under
# Windows PowerShell 5.1 $PSScriptRoot is empty inside a param() default.
$script:StatusToken  = ''
$script:StatusLastAt = [datetime]::MinValue
# Consecutive reads that produced no usable heartbeat (diagnostic only -- a read
# failure no longer suppresses the POST, it only changes what the POST says).
$script:StatusMisses = 0
# The last heartbeat that WAS usable. It is what covers FlowTrak's
# delete+recreate gap without the panel flapping; see Send-PcStatus.
$script:StatusHbCache = $null
# Last state PUBLISHED to the blog: $null until the first successful POST, then
# $true/$false. Used to log state changes rather than every tick.
$script:FlowTrakState   = $null
# Timestamp of the last state-change line / periodic summary, and how many posts
# have gone out in the current FlowTrak-absent state.
$script:StatusSummaryAt = [datetime]::MinValue
$script:StatusAbsent    = 0
if (-not $NoStatus) {
    if (-not $StatusTokenFile) { $StatusTokenFile = Join-Path $ScriptDir 'pc-status-token.txt' }
    $script:StatusToken = Get-StatusToken
    if ($script:StatusToken) {
        # The LENGTH only. The value never reaches a log, a console, or a command line.
        Write-Log "status reporter: token loaded from $StatusTokenFile ($($script:StatusToken.Length) chars) -> $StatusUrl every ${StatusEvery}s"
    } else {
        Write-Log "status reporter: DISABLED -- no usable token in $StatusTokenFile" 'WARN'
    }
}

try { Set-Content -LiteralPath $PidFile -Value $PID -Encoding ascii } catch { }

$python = $null
if (-not $NoService) {
    $python = Resolve-Python
    if (-not $python) { Write-Log 'no Python with Pillow+numpy found -- service can NOT be started' 'ERROR' }
    else { Write-Log "python for the service: $python" }
}

$backoff = $BackoffMin
$attempt = 0

$sshArgs = @(
    '-i', $SshKey
    '-N'
    '-R', "${RemotePort}:${LocalHost}:${LocalPort}"
    '-o', 'ServerAliveInterval=30'
    '-o', 'ServerAliveCountMax=3'
    '-o', 'ExitOnForwardFailure=yes'
    '-o', 'ConnectTimeout=15'
    # BatchMode: never sit on a password prompt in an unattended loop.
    '-o', 'BatchMode=yes'
    # The scheduled task has no interactive host-key prompt to answer.
    '-o', 'StrictHostKeyChecking=accept-new'
    $SshTarget
)

while ($true) {
    # ── 1. the local render service ─────────────────────────────────────────────
    Ensure-RenderService

    # ── 2. headless Chrome -- the WebGL engine's render device ──────────────────
    Ensure-Chrome

    # ── 2b. the blog's heartbeat ────────────────────────────────────────────────
    # Not a guard: it reports on the two above rather than restarting anything.
    # Self-throttled to once every $StatusEvery seconds and fully guarded, so a
    # blog that is down (or a network that is) cannot delay the tunnel.
    Send-PcStatus

    # ── 3. the reverse tunnel ───────────────────────────────────────────────────
    $attempt++
    $startedAt = Get-Date
    $held = 0
    Remove-Item -LiteralPath $SshErrFile -Force -ErrorAction SilentlyContinue

    Write-Log "tunnel attempt #${attempt}: ssh -N -R ${RemotePort}:${LocalHost}:${LocalPort} $SshTarget"
    $proc = $null
    # -NoNewWindow makes ssh inherit this process's (hidden) console, so it gets no window
    # of its own. It requires the caller to HAVE a console; if that ever fails, fall back
    # to an explicitly hidden new console rather than letting a window appear.
    try {
        $proc = Start-Process -FilePath $SshExe -ArgumentList $sshArgs -PassThru -NoNewWindow `
            -RedirectStandardError $SshErrFile -RedirectStandardOutput $SshOutFile `
            -ErrorAction Stop
    } catch {
        Write-Log "ssh launch with -NoNewWindow failed ($($_.Exception.Message)); retrying hidden" 'WARN'
        try {
            $proc = Start-Process -FilePath $SshExe -ArgumentList $sshArgs -PassThru -WindowStyle Hidden `
                -RedirectStandardError $SshErrFile -RedirectStandardOutput $SshOutFile `
                -ErrorAction Stop
        } catch {
            Write-Log "could not launch ssh: $($_.Exception.Message)" 'ERROR'
        }
    }

    if ($proc) {
        Rotate-Log $TunnelLog
        $upLine = '{0} --- tunnel up: pid={1} -R {2}:{3}:{4} ---' -f `
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $proc.Id, $RemotePort, $LocalHost, $LocalPort
        Add-Content -LiteralPath $TunnelLog -Encoding utf8 -Value $upLine
        # NOT a bare $proc.WaitForExit(): a healthy tunnel can hold for days, and waiting on
        # it here would mean nothing else -- the render service, Chrome -- is ever checked
        # while the node is at its most "up". Poll instead, and re-run the checks in between.
        while (-not $proc.HasExited) {
            Start-Sleep -Seconds $HealthEvery
            Ensure-RenderService
            Ensure-Chrome
            Send-PcStatus
        }
        $rc = $null
        try { $rc = $proc.ExitCode } catch { }
        $held = [int]((Get-Date) - $startedAt).TotalSeconds
        Write-Log "tunnel pid=$($proc.Id) exited rc=$rc after ${held}s" 'WARN'

        # Keep ssh's own diagnostics: this is where "remote port forwarding failed",
        # "Connection refused", "Permission denied" and the keepalive timeouts appear.
        try {
            if (Test-Path -LiteralPath $SshErrFile) {
                $err = (Get-Content -LiteralPath $SshErrFile -Raw -ErrorAction SilentlyContinue)
                if ($err -and $err.Trim()) {
                    Add-Content -LiteralPath $TunnelLog -Encoding utf8 -Value $err.Trim()
                    Write-Log ("ssh stderr: " + ($err.Trim() -replace '\s+', ' ')) 'WARN'
                }
            }
        } catch { }
    }

    # A session that lasted a while was healthy; a blip should not inherit a big backoff.
    if ($held -ge $HealthyAfter) { $backoff = $BackoffMin }

    Rotate-Log $SupervisorLog
    Write-Log "reconnecting in ${backoff}s"
    Start-Sleep -Seconds $backoff
    $backoff = [Math]::Min($BackoffMax, $backoff * 2)
}
