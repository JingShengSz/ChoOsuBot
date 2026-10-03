# Measure the peak resident memory of a server-side video render, across the whole
# process tree (the renderer fans frames out to a ProcessPoolExecutor, so the parent's
# own RSS badly understates the real cost).
#
#   pwsh -File mem_tree.ps1 -Skin "owc (default)" -Seconds 2
param(
  [string]$Skin = "owc (default)",
  [double]$Seconds = 2.0,
  [string]$Python = "C:\Users\OwO\AppData\Local\Python\pythoncore-3.14-64\python.exe",
  [string]$Root = "D:\DeepSeek Harness\workspace\osu-mania-render",
  # ffmpeg is part of the render's cost: it receives rawvideo 1920x1080 rgb24 over a
  # pipe and runs x264 with one thread per core, so the python-only sum understates it.
  [string[]]$Names = @("python", "ffmpeg")
)

$ErrorActionPreference = "Continue"
Set-Location $Root

$before = @()
foreach ($n in $Names) {
  $before += (Get-Process $n -ErrorAction SilentlyContinue).Id
}
$ffBefore = (Get-Process ffmpeg -ErrorAction SilentlyContinue).Id
"pre-existing pids: $($before -join ', ')  (ffmpeg: $(($ffBefore -join ', ')))"

$log = Join-Path $env:TEMP "mem_tree_out.txt"
# Start-Process joins -ArgumentList with spaces and does not quote, so a skin key with
# spaces/parens ("owc (default)") arrives as several argv entries. Quote it by hand.
$args = "tools\mem_probe.py --render $Seconds --only-render --skin `"$Skin`""
$p = Start-Process -FilePath $Python `
  -ArgumentList $args `
  -WorkingDirectory $Root -NoNewWindow -PassThru `
  -RedirectStandardOutput $log -RedirectStandardError "$log.err"

$peakSum = 0.0
$peakN = 0
$peakDetail = ""
$sums = @()
$peakAt = -1
while (-not $p.HasExited) {
  $news = @()
  foreach ($n in $Names) {
    $news += Get-Process $n -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id }
  }
  if ($news) {
    $s = ($news | Measure-Object -Property WorkingSet64 -Sum).Sum / 1MB
    $n = $news.Count
    $sums += ("{0:N0}/{1}" -f $s, $n)
    if ($s -gt $peakSum) {
      $peakSum = $s
      $peakN = $n
      $peakAt = $sums.Count - 1
      $peakDetail = ($news | Sort-Object WorkingSet64 -Descending |
        Select-Object -First 6 | ForEach-Object {
          "{0}:{1:N0}MB" -f $_.ProcessName, ($_.WorkingSet64 / 1MB)
        }) -join "  "
    }
  }
  Start-Sleep -Milliseconds 200
}
$p.WaitForExit()

""
"skin            : $Skin"
"seconds         : $Seconds"
"peak tree RSS   : $([math]::Round($peakSum,1)) MB   across $peakN processes   (sample #$peakAt)"
"top processes   : $peakDetail"
""
"samples (MB/count, 200ms apart):"
($sums -join "  ")
""
"--- probe stdout ---"
Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 14
$err = Get-Content "$log.err" -ErrorAction SilentlyContinue | Select-Object -Last 6
if ($err) { "--- probe stderr ---"; $err }
Remove-Item $log, "$log.err" -ErrorAction SilentlyContinue
