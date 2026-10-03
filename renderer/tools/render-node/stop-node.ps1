<#
    Stop the render node: remove the Scheduled Task (optional) and kill the supervisor,
    its ssh tunnel, the local render service and the headless Chrome the supervisor owns.

    Usage
    -----
        pwsh -File stop-node.ps1                 # stop the node, keep the Scheduled Task
        pwsh -File stop-node.ps1 -RemoveTask     # also uninstall the Scheduled Task
        pwsh -File stop-node.ps1 -KeepService    # leave the render service running
        pwsh -File stop-node.ps1 -KeepChrome     # leave Chrome running
#>

[CmdletBinding()]
param(
    [string] $TaskName    = 'ManiaRenderNode',
    [int]    $RemotePort  = 8760,
    [int]    $LocalPort   = 8760,
    [int]    $ChromePort  = 9222,
    [string] $ChromeProfile = 'D:\DeepSeek Harness\workspace\osu-mania-render\cache\chrome-gpu-profile',
    [switch] $RemoveTask,
    [switch] $KeepService,
    [switch] $KeepChrome
)

$ErrorActionPreference = 'Continue'

$LogDir  = Join-Path $PSScriptRoot 'logs'
$PidFile = Join-Path $LogDir 'render-node.pid'

function Say { param([string] $m) Write-Host $m }

# ── 1. the Scheduled Task ───────────────────────────────────────────────────────
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -eq 'Running') { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Say "task stopped: $TaskName" }
    else { Say "task present but not running: $TaskName" }
    if ($RemoveTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Say "task removed: $TaskName"
    }
} else { Say "no task named $TaskName" }

# ── 2. the supervisor process (from the pid file) ───────────────────────────────
if (Test-Path -LiteralPath $PidFile) {
    $sup = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue)
    if ($sup) {
        $sup = $sup.Trim()
        $p = Get-Process -Id $sup -ErrorAction SilentlyContinue
        if ($p) {
            # Kill the whole tree: powershell -> ssh. Children first.
            $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$sup" -ErrorAction SilentlyContinue
            foreach ($k in $kids) { Stop-Process -Id $k.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $sup -Force -ErrorAction SilentlyContinue
            Say "supervisor pid $sup stopped (with $($kids.Count) child process(es))"
        } else { Say "supervisor pid $sup is not running" }
    }
} else { Say "no pid file at $PidFile" }

# ── 3. belt and braces: any ssh still holding our remote forward ────────────────
$stale = @(Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "-R\s+$RemotePort`:" })
foreach ($s in $stale) {
    Stop-Process -Id $s.ProcessId -Force -ErrorAction SilentlyContinue
    Say "stale tunnel pid $($s.ProcessId) stopped"
}
if (-not $stale.Count) { Say "no ssh process is holding -R ${RemotePort}:" }

# ── 4. the local render service (only if it is ours on the port) ────────────────
if (-not $KeepService) {
    $conns = @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue)
    $killed = 0
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match '^python') {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Say "render service pid $($proc.Id) stopped"
            $killed++
        }
    }
    if (-not $killed) { Say "no python render service listening on $LocalPort" }
}

# ── 5. the headless Chrome the supervisor owns (the WebGL engine's render device) ──
# Matched on the dedicated profile directory, so nothing of the user's own browser is
# touched. Without this a "stopped" node still answers on 9222 and still holds the GPU.
if (-not $KeepChrome) {
    $victims = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($ChromeProfile) })
    foreach ($c in $victims) {
        Stop-Process -Id $c.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($victims.Count) { Say "chrome ($ChromePort) stopped: $($victims.Count) process(es)" }
    else { Say "no chrome.exe running under $ChromeProfile" }
}

Say 'done.'
