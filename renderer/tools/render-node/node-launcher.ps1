<#
    node-launcher.ps1 — the backend behind the two Desktop launchers
    ===============================================================

        C:\Users\OwO\Desktop\启动渲染节点.cmd   ->  -Action Start
        C:\Users\OwO\Desktop\检查渲染节点.cmd   ->  -Action Check

    Both .cmd files are deliberately trivial: they only set the console codepage, call this
    script with -Action, and pause. All of the logic lives HERE, next to the node's own
    scripts, so it is versioned with them and the two Desktop files can never drift apart.

    Why one script and not two
    -------------------------
    Start and Check must report the SAME five things — if the checks lived in two files they
    would drift, and the launcher would start telling the user something different from what
    it verifies. Start = (make it run) + (Check). So the checks are written once.

    What is checked, in this order
    ------------------------------
      1. 渲染服务   127.0.0.1:8760  GET /api/skins -> 200
      2. Chrome    127.0.0.1:9222  CDP answers AND the LIVE WebGL renderer string is
                                    D3D11/NVIDIA. Deliberately not a command-line flag
                                    check: a Chrome that silently fell back to SwiftShader
                                    still carries the flags and still "works" — it is just
                                    ~7x slower (35 fps vs 259 fps, measured), which is the
                                    worst possible failure: it looks healthy.
      3. 隧道       verified FROM THE SERVER SIDE. ssh to the VPS and curl ITS
                    127.0.0.1:8760. The reply must contain this machine's Windows paths
                    (D:\...). A local-only check would pass while the tunnel was dead.
      4. 上报       the blog 主机状态 panel is fed by a POST every ~60 s; the supervisor
                    logs each one. We read the last success out of that log.
      5. 计划任务   its State, so the user can see Running.

    Never prints the status token, and never prints window titles (this node's rule: titles
    are dropped from its logs, and they are nobody else's business).

    No administrator rights are needed or requested anywhere.
#>

[CmdletBinding()]
param(
    [ValidateSet('Start','Check')]
    [string] $Action = 'Check',

    [string] $TaskName       = 'ManiaRenderNode',
    [string] $SshTarget      = 'root@www.liuliyue.com',
    [string] $SshKey         = "$env:USERPROFILE\.ssh\id_ed25519",
    [int]    $LocalPort      = 8760,
    [int]    $ChromePort     = 9222,
    [int]    $TimeoutSeconds = 90,
    [switch] $NoAutoFix
)

$ErrorActionPreference = 'Continue'

$Here           = $PSScriptRoot
$Vbs            = Join-Path $Here 'run-hidden.vbs'
$SupervisorPs1  = Join-Path $Here 'render-node.ps1'
$LogDir         = Join-Path $Here 'logs'
$PidFile        = Join-Path $LogDir 'render-node.pid'
$SupervisorLog  = Join-Path $LogDir 'supervisor.log'
$TunnelLog      = Join-Path $LogDir 'tunnel.log'
$ClearTunnelSh  = Join-Path $Here 'clear-wedged-tunnel.sh'

$SshExe = "$env:WINDIR\System32\OpenSSH\ssh.exe"
if (-not (Test-Path -LiteralPath $SshExe)) { $SshExe = 'ssh.exe' }

# Native output (ssh.exe, curl) is UTF-8; without this the skin paths come back as mojibake
# under Windows PowerShell 5.1, which decodes native stdout with the ANSI codepage.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ─────────────────────────────── output helpers ─────────────────────────────────

# CJK glyphs occupy two console columns; PadRight counts characters, so aligning a mixed
# Chinese/ASCII status list with it produces a ragged edge. This measures real columns.
function Get-DisplayWidth {
    param([string] $Text)
    $w = 0
    foreach ($ch in $Text.ToCharArray()) {
        $c = [int]$ch
        if (($c -ge 0x1100 -and $c -le 0x115F) -or
            ($c -ge 0x2E80 -and $c -le 0xA4CF) -or
            ($c -ge 0xAC00 -and $c -le 0xD7A3) -or
            ($c -ge 0xF900 -and $c -le 0xFAFF) -or
            ($c -ge 0xFE30 -and $c -le 0xFE6F) -or
            ($c -ge 0xFF00 -and $c -le 0xFF60) -or
            ($c -ge 0xFFE0 -and $c -le 0xFFE6)) { $w += 2 } else { $w += 1 }
    }
    return $w
}

function Pad-Display {
    param([string] $Text, [int] $Width)
    $pad = $Width - (Get-DisplayWidth $Text)
    if ($pad -lt 0) { $pad = 0 }
    return $Text + (' ' * $pad)
}

function Write-Head {
    param([string] $Title)
    Write-Host ''
    Write-Host ('  ' + $Title) -ForegroundColor White
    Write-Host ('  ' + ('-' * 62)) -ForegroundColor DarkGray
}

function Write-Item {
    param([string] $Name, [bool] $Ok, [string] $Detail)
    $mark  = if ($Ok) { [char]0x2713 } else { [char]0x2717 }   # ✓ / ✗
    $color = if ($Ok) { 'Green' } else { 'Red' }
    Write-Host '   ' -NoNewline
    Write-Host $mark -NoNewline -ForegroundColor $color
    Write-Host ' ' -NoNewline
    Write-Host (Pad-Display $Name 12) -NoNewline -ForegroundColor Gray
    Write-Host $Detail
}

function Write-Note {
    param([string] $Text, [string] $Color = 'DarkGray')
    Write-Host ("      " + $Text) -ForegroundColor $Color
}

# ─────────────────────────── raw HTTP to a loopback port ────────────────────────
# Not Invoke-WebRequest: under the Scheduled Task's Windows PowerShell 5.1 its defaults drag
# in the IE engine, it honours a system proxy that has no business proxying 127.0.0.1, and
# it throws instead of returning a status code. This is the same shape the supervisor uses.
function Invoke-LocalHttpGet {
    param(
        [string] $TargetHost = '127.0.0.1',
        [int]    $Port,
        [string] $Path = '/',
        [int]    $TimeoutMs = 4000
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $null }
        $client.EndConnect($iar)
        $stream = $client.GetStream()
        $stream.ReadTimeout  = $TimeoutMs
        $stream.WriteTimeout = $TimeoutMs
        $req = [System.Text.Encoding]::ASCII.GetBytes(
            "GET $Path HTTP/1.1`r`nHost: ${TargetHost}:$Port`r`nAccept: */*`r`nConnection: close`r`n`r`n")
        $stream.Write($req, 0, $req.Length)

        $ms      = New-Object System.IO.MemoryStream
        $buf     = New-Object byte[] 8192
        $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
        while ((Get-Date) -lt $deadline) {
            $n = 0
            try { $n = $stream.Read($buf, 0, $buf.Length) } catch { break }
            if ($n -le 0) { break }
            $ms.Write($buf, 0, $n)
        }
        $raw = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
        $code = 0
        if ($raw -match '^HTTP/\d\.\d\s+(\d{3})') { $code = [int]$Matches[1] }
        return [pscustomobject]@{ Code = $code; Raw = $raw }
    } catch {
        return $null
    } finally { $client.Close() }
}

# ───────────────────────── 1. the render service ────────────────────────────────

function Test-RenderService {
    $r = Invoke-LocalHttpGet -Port $LocalPort -Path '/api/skins' -TimeoutMs 4000
    if (-not $r) {
        return @{ Ok = $false; Detail = "连接失败 — 127.0.0.1:$LocalPort 上没有服务在监听" }
    }
    if ($r.Code -ne 200) {
        return @{ Ok = $false; Detail = "HTTP $($r.Code)（期望 200）" }
    }
    $count = 0
    if ($r.Raw -match '"skins"') {
        $count = ([regex]::Matches($r.Raw, '"key"\s*:')).Count
    }
    return @{ Ok = $true; Detail = "HTTP 200  /api/skins  ($count 个皮肤)" }
}

# ───────────────────── 2. headless Chrome + its REAL renderer ───────────────────

function Get-CdpWebglRenderer {
    param([int] $TimeoutMs = 6000)
    $list = Invoke-LocalHttpGet -Port $ChromePort -Path '/json/list' -TimeoutMs 3000
    if (-not $list -or $list.Code -ne 200) { return $null }
    $json = $list.Raw
    $idx  = $json.IndexOf('[')
    if ($idx -lt 0) { return $null }
    $body = $json.Substring($idx)
    $targets = $null
    try { $targets = $body | ConvertFrom-Json } catch { return $null }
    $page = $targets | Where-Object { $_.type -eq 'page' -and $_.webSocketDebuggerUrl } | Select-Object -First 1
    if (-not $page) { return $null }

    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $ct = [System.Threading.CancellationToken]::None
    try {
        $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait($TimeoutMs) | Out-Null
        if ($ws.State -ne 'Open') { return $null }

        $js = @'
(() => {
  try {
    var c = document.createElement('canvas');
    var gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) return 'NO_WEBGL';
    var e = gl.getExtension('WEBGL_debug_renderer_info');
    return e ? String(gl.getParameter(e.UNMASKED_RENDERER_WEBGL))
             : ('RAW:' + gl.getParameter(gl.RENDERER));
  } catch (err) { return 'ERR:' + err.message; }
})()
'@
        $payload = @{ id = 1; method = 'Runtime.evaluate'
                      params = @{ expression = $js; returnByValue = $true } } |
                   ConvertTo-Json -Depth 6 -Compress
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
        $seg   = New-Object System.ArraySegment[byte] -ArgumentList @(,$bytes)
        $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait($TimeoutMs) | Out-Null

        $buf = New-Object byte[] 65536
        $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
        while ((Get-Date) -lt $deadline) {
            $seg2 = New-Object System.ArraySegment[byte] -ArgumentList @(,$buf)
            $task = $ws.ReceiveAsync($seg2, $ct)
            $left = [int]($deadline - (Get-Date)).TotalMilliseconds
            if ($left -le 0) { break }
            if (-not $task.Wait($left)) { break }
            $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $task.Result.Count)
            if ($text -match '"id"\s*:\s*1') {
                try {
                    $obj = $text | ConvertFrom-Json
                    return [string]$obj.result.result.value
                } catch { return $null }
            }
        }
        return $null
    } catch {
        return $null
    } finally { try { $ws.Dispose() } catch { } }
}

function Test-Chrome {
    $ver = Invoke-LocalHttpGet -Port $ChromePort -Path '/json/version' -TimeoutMs 3000
    if (-not $ver -or $ver.Code -ne 200 -or $ver.Raw -notmatch '"Browser"') {
        return @{ Ok = $false; Renderer = ''; Detail = "CDP 无响应 — 127.0.0.1:$ChromePort 不通（没有无头 Chrome）" }
    }
    $browser = '?'
    if ($ver.Raw -match '"Browser"\s*:\s*"([^"]+)"') { $browser = $Matches[1] }

    $renderer = Get-CdpWebglRenderer
    if (-not $renderer) {
        return @{ Ok = $false; Renderer = ''; Detail = "CDP 已响应 ($browser)，但读不到 WebGL 渲染器" }
    }
    # Software fallback FIRST: its string carries no NVIDIA/AMD, and it is the failure that
    # looks like success. ~7x slower while every other check passes.
    if ($renderer -match 'SwiftShader|Software|llvmpipe|Basic Render') {
        return @{ Ok = $false; Renderer = $renderer
                  Detail = "软件渲染！$renderer — 比 GPU 慢约 7 倍（会渲染成功但极慢）" }
    }
    if ($renderer -match 'D3D11|Direct3D11|NVIDIA|Radeon|Intel\(R\)|AMD') {
        return @{ Ok = $true; Renderer = $renderer; Detail = $renderer }
    }
    return @{ Ok = $false; Renderer = $renderer; Detail = "渲染器不是 D3D11/NVIDIA：$renderer" }
}

# ────────────────── 3. the tunnel, verified from the SERVER SIDE ────────────────

function Invoke-VpsBash {
    param([string] $Script, [int] $ConnectTimeout = 8)
    if (-not (Test-Path -LiteralPath $SshKey)) {
        return [pscustomobject]@{ Out = "SSH_KEY_MISSING: $SshKey"; Code = 255 }
    }
    $clean = $Script -replace "`r", ''
    $out = $clean | & $SshExe -i $SshKey `
        -o ConnectTimeout=$ConnectTimeout -o BatchMode=yes `
        -o StrictHostKeyChecking=accept-new `
        -o ServerAliveInterval=5 -o ServerAliveCountMax=2 `
        $SshTarget "tr -d '\r' | bash -s" 2>&1
    return [pscustomobject]@{ Out = ($out -join "`n"); Code = $LASTEXITCODE }
}

function Test-Tunnel {
    # Ask the VPS itself. Its own 127.0.0.1:8760 is an sshd reverse-forward listener that
    # lands on this machine, so a reply carrying Windows paths can ONLY have come through
    # the tunnel. Checking locally would prove nothing.
    $bash = @'
echo "LISTENER=$(ss -lntp 2>/dev/null | grep -c '127.0.0.1:8760')"
curl -s -m 8 -w "\nCODE=%{http_code}" http://127.0.0.1:8760/api/skins
'@
    $r = Invoke-VpsBash -Script $bash
    if ($r.Out -match 'SSH_KEY_MISSING') {
        return @{ Ok = $false; Detail = "找不到 SSH 私钥：" + $SshKey; Kind = 'key' }
    }
    if ($r.Out -match 'Permission denied|Host key verification failed') {
        return @{ Ok = $false; Detail = "SSH 登录被拒（密钥或指纹问题）"; Kind = 'auth' }
    }
    if ($r.Out -match 'Connection timed out|Connection refused|No route to host|Could not resolve') {
        return @{ Ok = $false; Detail = "连不上 VPS $SshTarget（网络不通或被墙）"; Kind = 'net' }
    }
    if ($r.Code -ne 0 -and $r.Out -notmatch 'CODE=') {
        return @{ Ok = $false; Detail = "ssh 执行失败：$(($r.Out -split "`n" | Select-Object -First 1))"; Kind = 'ssh' }
    }
    $hasWindowsPath = ($r.Out -match '[A-Za-z]:\\\\')
    $code = '?'
    if ($r.Out -match 'CODE=(\d{3})') { $code = $Matches[1] }

    if ($code -eq '200' -and $hasWindowsPath) {
        # The reply is JSON, so its paths arrive double-escaped ("D:\\osu-lazer\\..."). Show
        # one real path with single separators -- it is the whole proof, and `D:\\` reads
        # like a typo.
        $example = ''
        if ($r.Out -match '(D:\\\\[^"]{0,80}?\.osk)') {
            $example = ' 例：' + ($Matches[1] -replace '\\\\', '\')
        }
        return @{ Ok = $true; Detail = "服务器侧 curl HTTP 200，返回本机 Windows 路径$example"; Kind = 'ok' }
    }
    if ($code -eq '200' -and -not $hasWindowsPath) {
        return @{ Ok = $false; Detail = "服务器侧 200，但返回的不是本机内容（8760 被别的程序占了？）"; Kind = 'impostor' }
    }
    if ($r.Out -match 'LISTENER=1') {
        return @{ Ok = $false; Detail = "VPS 上 8760 有人监听，但请求超时（僵死的 ssh 转发占着端口）"; Kind = 'wedged' }
    }
    return @{ Ok = $false; Detail = "服务器侧 127.0.0.1:8760 拒绝连接（隧道未建立）"; Kind = 'down' }
}

# A wedged forward: the Windows ssh died (network drop / reboot) but the VPS-side sshd child
# still holds a listener on 8760, so the new tunnel cannot bind and ssh exits with
#   "Error: remote port forwarding failed for listen port 8760"
# The listener black-holes: it accepts the connection and then times out. This is the single
# most likely thing to meet the user after a reboot, so the launcher repairs it — but only
# when that exact signature is in the log, and only ever the sshd that owns 8760.
function Get-TunnelLogTail {
    param([int] $Lines = 25)
    if (-not (Test-Path -LiteralPath $TunnelLog)) { return '' }
    $t = Get-Content -LiteralPath $TunnelLog -Tail $Lines -ErrorAction SilentlyContinue
    if (-not $t) { return '' }
    return ($t -join "`n")
}

function Repair-WedgedForward {
    if ($NoAutoFix) { return $false }
    if ((Get-TunnelLogTail) -notmatch 'remote port forwarding failed for listen port 8760') { return $false }
    if (-not (Test-Path -LiteralPath $ClearTunnelSh)) { return $false }

    Write-Note '  → VPS 上 8760 被上次遗留的僵死 ssh 会话占用，正在清理…' 'Yellow'
    $sh  = Get-Content -LiteralPath $ClearTunnelSh -Raw
    $r   = Invoke-VpsBash -Script $sh -ConnectTimeout 10
    if ($r.Out -match '8760 now FREE' -or $r.Out -match 'nothing to clear') {
        Write-Note '  → 已清理，等待隧道重连…' 'Yellow'
        return $true
    }
    Write-Note ("  → 清理未成功：" + (($r.Out -split "`n" | Select-Object -First 2) -join ' ')) 'DarkYellow'
    return $false
}

# ───────────────────────────── 4. the blog heartbeat ────────────────────────────
# The blog's panel is POST-only (a GET answers 405), so the authoritative local question is
# "when did the supervisor last POST successfully?" — which it logs.
function Get-ReportStatus {
    if (-not (Test-Path -LiteralPath $SupervisorLog)) {
        return @{ Ok = $false; Detail = '读不到 logs\supervisor.log，无法判断上报状态' }
    }
    $tail = Get-Content -LiteralPath $SupervisorLog -Tail 400 -ErrorAction SilentlyContinue
    if (-not $tail) { return @{ Ok = $false; Detail = 'supervisor.log 是空的' } }

    $lastOk = $null; $lastOkCode = ''; $lastFail = $null
    foreach ($line in $tail) {
        # Only the timestamp and the HTTP code are ever taken — never the app= field, which
        # is a foreground-process name we have no reason to print.
        if ($line -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*heartbeat posted \(HTTP (\d+)') {
            $lastOk = $Matches[1]; $lastOkCode = $Matches[2]
        } elseif ($line -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*status reporter: POST failed') {
            $lastFail = $Matches[1]
        }
    }
    if (-not $lastOk) {
        return @{ Ok = $false; Detail = '日志里没有成功上报的记录（最近 400 行）' }
    }
    $when = [datetime]::MinValue
    $parsed = [datetime]::TryParseExact($lastOk, 'yyyy-MM-dd HH:mm:ss', $null,
              [System.Globalization.DateTimeStyles]::None, [ref]$when)
    if (-not $parsed) { return @{ Ok = $true; Detail = "最近一次上报 $lastOk (HTTP $lastOkCode)" } }

    $age = [int]((Get-Date) - $when).TotalSeconds
    if ($age -le 150) {
        return @{ Ok = $true; Detail = "博客面板显示在线 — ${age} 秒前上报成功 (HTTP $lastOkCode)" }
    }
    $mins = [int]($age / 60)
    $extra = if ($lastFail) { "；最近有失败记录 $lastFail（面板会显示离线）" } else { '' }
    return @{ Ok = $false; Detail = "已 ${mins} 分钟没有成功上报 — 博客面板会显示离线$extra" }
}

# ───────────────────────────── 5. the Scheduled Task ────────────────────────────
function Get-TaskState {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) {
        return @{ Exists = $false; State = '不存在'; Task = $null }
    }
    return @{ Exists = $true; State = [string]$t.State; Task = $t }
}

function Get-SupervisorPid {
    if (-not (Test-Path -LiteralPath $PidFile)) { return 0 }
    $raw = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue)
    if (-not $raw) { return 0 }
    $n = 0
    if ([int]::TryParse($raw.Trim(), [ref]$n)) { return $n }
    return 0
}

# ───────────────────────────────── the check run ────────────────────────────────

function Invoke-NodeChecks {
    $svc  = Test-RenderService
    $gpu  = Test-Chrome
    $tun  = Test-Tunnel
    $rep  = Get-ReportStatus
    $task = Get-TaskState

    Write-Head '检查结果'
    Write-Item '渲染服务' $svc.Ok $svc.Detail
    Write-Item 'Chrome'   $gpu.Ok $gpu.Detail
    Write-Item '隧道'     $tun.Ok $tun.Detail
    Write-Item '上报'     $rep.Ok $rep.Detail
    Write-Item '计划任务' $task.Exists ("{0}：{1}" -f $TaskName, $task.State)
    if (-not $task.Exists) {
        Write-Note '任务未注册 → 电脑重启/重新登录后节点不会自启，请运行 install-task.ps1' 'Yellow'
    }

    return @{ Svc = $svc; Gpu = $gpu; Tun = $tun; Rep = $rep; Task = $task }
}

function Write-Hints {
    param($R)
    $hints = @()
    if (-not $R.Task.Exists) {
        $hints += '计划任务未注册，请运行 install-task.ps1（否则每次开机都要手动点这个启动器）'
    }
    if (-not $R.Svc.Ok) {
        $hints += '渲染服务没起来：多半是 Python 依赖（Pillow / numpy）或端口被占，看 logs\render-service.err.log'
    }
    if ($R.Svc.Ok -and -not $R.Gpu.Ok) {
        if ($R.Gpu.Renderer -match 'SwiftShader|Software') {
            $hints += 'Chrome 退回了软件渲染（SwiftShader）：它照样能渲染，但慢约 7 倍，必须重启节点'
        } else {
            $hints += '无头 Chrome 没跑起来或没带 GPU 参数：运行 stop-node.ps1 再启动一次'
        }
    }
    if (-not $R.Tun.Ok) {
        switch ($R.Tun.Kind) {
            'net'      { $hints += '连不上 VPS：先确认这台电脑能上外网、代理没挡住 SSH(22)' }
            'wedged'   { $hints += 'VPS 上 8760 被上一次遗留的 ssh 会话僵死占用：运行 clear-wedged-tunnel.sh 对应的清理命令' }
            'down'     { $hints += '隧道没建立：supervisor 没在跑，或 VPS 的 SSH 拒绝转发' }
            'key'      { $hints += "SSH 私钥不存在：$SshKey" }
            'impostor' { $hints += 'VPS 的 8760 应答的不是本机内容：确认 mania-render.service 仍是 inactive+disabled' }
            default    { $hints += '隧道异常：看 logs\tunnel.log 最后几行' }
        }
    }
    if (-not $R.Rep.Ok) {
        $hints += '上报失败不影响渲染，只影响博客首页的「主机状态」面板是否显示在线'
    }

    # The ones the user is most likely to meet. Stated as facts about how this node is
    # wired, not as claims about the current failure, so they are safe to always show.
    $hints += '电脑未登录 Windows，节点不会自启（计划任务是「登录时」触发，不是开机触发）'
    $hints += 'FlowTrak 未运行不影响渲染（它只喂博客面板的前台应用名）'

    $seen = @{}
    $uniq = @()
    foreach ($h in $hints) { if (-not $seen.ContainsKey($h)) { $seen[$h] = $true; $uniq += $h } }

    Write-Host ''
    Write-Host '  可能的原因（按可能性排序）：' -ForegroundColor Yellow
    $i = 1
    foreach ($h in ($uniq | Select-Object -First 6)) {
        Write-Host ("    $i. " + $h) -ForegroundColor Yellow
        $i++
    }
}

# ─────────────────────────────────── the start ──────────────────────────────────

function Wait-ForHealthy {
    param([int] $TimeoutSeconds)

    $start   = Get-Date
    $overall = $start.AddSeconds($TimeoutSeconds)
    $phaseA  = $start.AddSeconds([Math]::Min(45, $TimeoutSeconds))

    # Phase A — the two local components. Fast, no network, polled tightly.
    $svc = $null; $gpu = $null
    while ((Get-Date) -lt $phaseA) {
        $svc = Test-RenderService
        $gpu = Test-Chrome
        if ($svc.Ok -and $gpu.Ok) { break }
        Start-Sleep -Seconds 2
    }
    if (-not ($svc -and $svc.Ok -and $gpu -and $gpu.Ok)) { return $false }

    # Phase B — the tunnel, which needs the VPS. Polled loosely: each probe is an ssh.
    # The supervisor's own ssh backoff can reach 60 s, so this window has to cover it.
    $repaired = $false
    while ((Get-Date) -lt $overall) {
        $tun = Test-Tunnel
        if ($tun.Ok) { return $true }
        if (-not $repaired -and $tun.Kind -eq 'wedged') {
            [void](Repair-WedgedForward)
            $repaired = $true
        }
        Start-Sleep -Seconds 5
    }
    return $false
}

function Start-Node {
    Write-Head '启动'
    $supPid   = Get-SupervisorPid
    $supAlive = $false
    if ($supPid -gt 0) {
        $p = Get-Process -Id $supPid -ErrorAction SilentlyContinue
        if ($p) { $supAlive = $true }
    }
    $task = Get-TaskState

    if ($supAlive) {
        Write-Item '已在运行' $true "supervisor pid $supPid — 跳过启动（不会重复启动）"
        Write-Note '若某个组件掉线，supervisor 每 15 秒自查一次会自动拉起，下面直接验证。'
        return $true
    }

    if ($task.Exists) {
        Write-Note "方式：计划任务 $TaskName (Start-ScheduledTask)"
        try {
            Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        } catch {
            Write-Item '启动失败' $false "Start-ScheduledTask 报错：$($_.Exception.Message)"
            if ($_.Exception.Message -match 'Access is denied|拒绝访问') {
                Write-Note '这个操作需要管理员权限。请右键以管理员身份运行 install-task.ps1 重新注册任务，' 'Red'
                Write-Note '或者直接用本机的 render-node.ps1 手动前台启动（不需要管理员）。' 'Red'
            }
            return $false
        }
        Start-Sleep -Seconds 3
        $now = Get-TaskState
        Write-Item '已下发启动' $true "任务状态现在：$($now.State)"
    }
    else {
        # No task: this is the fallback path, and it is NOT persistent across a reboot.
        Write-Note "方式：计划任务不存在 — 直接启动 supervisor（回退路径）" 'Yellow'
        if (-not (Test-Path -LiteralPath $Vbs)) {
            Write-Item '启动失败' $false "既没有计划任务，也找不到 $Vbs"
            return $false
        }
        try {
            Start-Process -FilePath "$env:WINDIR\System32\wscript.exe" -ArgumentList "`"$Vbs`"" -ErrorAction Stop
        } catch {
            Write-Item '启动失败' $false "wscript 启动 supervisor 出错：$($_.Exception.Message)"
            return $false
        }
        Write-Item '已启动 supervisor' $true '（回退路径：run-hidden.vbs，不是通过计划任务）'
        Write-Note '注意：这条路径不会在下次开机/登录时自动运行。要长期有效请运行 install-task.ps1。' 'Yellow'
    }
    return $true
}

function Show-WhyNotStarted {
    Write-Host ''
    Write-Host '  没能启动，原因：' -ForegroundColor Red
    $task = Get-TaskState
    Write-Note ("计划任务 $TaskName：" + $(if ($task.Exists) { "存在（状态 $($task.State)）" } else { '不存在 — 需要运行 install-task.ps1' }))
    Write-Note ("当前用户是否已登录交互会话：" + $(if ([Environment]::UserInteractive) { '是（本启动器本来就是登录后手动运行的）' } else { '否' }))
    $sup = Get-Process -Id (Get-SupervisorPid) -ErrorAction SilentlyContinue
    Write-Note ("supervisor 进程：" + $(if ($sup) { "在跑 (pid $($sup.Id))" } else { '不在' }))
    if ($task.Exists -and $task.State -eq 'Running' -and -not $sup) {
        Write-Note '任务显示 Running 但没有 supervisor 进程：这是上一次的残留。先运行 stop-node.ps1，再试一次。' 'Yellow'
    }
    Write-Note '本启动器不需要管理员权限；只有上面提示「需要管理员权限」时才需要。'
}

# ─────────────────────────────────── entry point ────────────────────────────────

try { $Host.UI.RawUI.WindowTitle = '渲染节点 — ' + $(if ($Action -eq 'Start') { '启动' } else { '检查' }) } catch { }

Write-Host ''
Write-Host '  ============================================================' -ForegroundColor DarkCyan
Write-Host ('   渲染节点  ' + $(if ($Action -eq 'Start') { '启动并验证' } else { '状态检查' })) -ForegroundColor Cyan
Write-Host ('   ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -ForegroundColor DarkGray
Write-Host '  ============================================================' -ForegroundColor DarkCyan

$started  = $true
$healthy  = $true

if ($Action -eq 'Start') {
    $started = Start-Node
    if ($started) {
        Write-Host ''
        Write-Host "  等待组件就绪（最长 $TimeoutSeconds 秒）…" -ForegroundColor DarkGray
        $healthy = Wait-ForHealthy -TimeoutSeconds $TimeoutSeconds
    } else {
        $healthy = $false
    }
}

$r = Invoke-NodeChecks

$passed = @($r.Svc.Ok, $r.Gpu.Ok, $r.Tun.Ok, $r.Rep.Ok).Where({ $_ }).Count
$total  = 4

Write-Host ''
if ($r.Svc.Ok -and $r.Gpu.Ok -and $r.Tun.Ok) {
    Write-Host ("  结论：渲染链路正常（{0}/{1}）" -f $passed, $total) -ForegroundColor Green
    Write-Host '  渲染服务、无头 Chrome(GPU)、隧道 三项都通，可以正常接单渲染。' -ForegroundColor DarkGray
    if (-not $r.Rep.Ok) {
        Write-Host '  （上报异常只影响博客面板显示，不影响渲染。）' -ForegroundColor DarkGray
    }
} else {
    Write-Host ("  结论：有问题（{0}/{1}）" -f $passed, $total) -ForegroundColor Red
    if (-not $started) { Show-WhyNotStarted }
    Write-Hints -R $r
}

if ($Action -eq 'Start' -and $started -and -not $healthy) {
    Write-Host ''
    Write-Host "  注意：等待 $TimeoutSeconds 秒后仍未全部就绪。" -ForegroundColor Yellow
}

Write-Host ''
$allOk = ($r.Svc.Ok -and $r.Gpu.Ok -and $r.Tun.Ok)
if ($allOk) { exit 0 } else { exit 1 }
