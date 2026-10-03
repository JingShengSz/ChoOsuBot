<#
    Install / remove the Scheduled Task that keeps the mania-render node alive.

    The task runs at LOGON of the current user and launches
        wscript.exe run-hidden.vbs
    which starts render-node.ps1 with no console window. render-node.ps1 is an infinite
    loop, so the task itself never exits; it only needs to be started once per logon.

    Why logon and not boot
    ----------------------
    A task that runs at BOOT while nobody is logged on must run as SYSTEM (or with
    "run whether user is logged on or not"), and registering that requires an
    administrator and, for a *user* account, a stored password. Registering either is
    refused with "Access is denied" for an unelevated user -- run `-ProbeBoot` to see
    the exact message on this machine. See README.md for the elevated commands.

    No admin rights are needed for what this script installs: a task in the current
    user's context with an AtLogOn trigger is something any user may create.

    Usage
    -----
        pwsh -File install-task.ps1                 # install + start now
        pwsh -File install-task.ps1 -ProbeBoot      # also probe why boot-start is refused
        pwsh -File install-task.ps1 -WhatIfOnly     # print what it would do, change nothing
        pwsh -File uninstall-task.ps1               # remove it
#>

[CmdletBinding()]
param(
    [string] $TaskName = 'ManiaRenderNode',
    [switch] $RunNow    = $true,
    [switch] $ProbeBoot,
    [switch] $WhatIfOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$here = $PSScriptRoot
$vbs  = Join-Path $here 'run-hidden.vbs'
$ps1  = Join-Path $here 'render-node.ps1'

foreach ($f in @($vbs, $ps1)) {
    if (-not (Test-Path -LiteralPath $f)) { throw "missing: $f" }
}

Write-Host "action : wscript.exe `"$vbs`""
Write-Host "script : $ps1"
Write-Host "task   : $TaskName  (trigger: at logon of $env:USERDOMAIN\$env:USERNAME)"

if ($WhatIfOnly) { Write-Host '(-WhatIfOnly: nothing was changed)'; return }

# ── build ───────────────────────────────────────────────────────────────────────
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\wscript.exe" -Argument "`"$vbs`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Interactive + Limited: the runner is the logged-on user, unelevated.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description 'Keeps the osu!mania render node up: local render service on 127.0.0.1:8760 plus the reverse SSH tunnel that makes the VPS 127.0.0.1:8760 land on this machine.' | Out-Null

Write-Host 'registered OK'
Get-ScheduledTask -TaskName $TaskName |
    Select-Object TaskName, State, @{n='Trigger';e={ ($_.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ',' }} |
    Format-List

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 6
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "started. LastTaskResult=$($info.LastTaskResult)  LastRunTime=$($info.LastRunTime)"
    Write-Host ''
    Write-Host '--- supervisor processes ---'
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object { $_.CommandLine -match '-R\s+8760:' } |
        Select-Object ProcessId, CommandLine | Format-List
}

# ── optional: why boot-start cannot be registered unelevated ────────────────────
if ($ProbeBoot) {
    Write-Host ''
    Write-Host '--- probing a boot-trigger task (expected to be refused) ---'
    $probe = 'ManiaRenderNodeBootProbe'
    $out = & schtasks.exe /Create /TN $probe /SC ONSTART /RU SYSTEM /TR "wscript.exe `"$vbs`"" 2>&1
    $rc = $LASTEXITCODE
    Write-Host "schtasks rc=$rc"
    $out | ForEach-Object { Write-Host "  $_" }
    if ($rc -eq 0) {
        Write-Host '  (unexpectedly succeeded -- removing the probe task)'
        & schtasks.exe /Delete /TN $probe /F 2>&1 | ForEach-Object { Write-Host "  $_" }
    }
    Write-Host ''
    Write-Host 'elevated? ' ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
