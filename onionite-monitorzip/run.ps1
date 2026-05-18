param(
    [int]$Interval = 30,
    [switch]$OpenBrowser,
    [switch]$Once,
    [switch]$ShowAll,
    [switch]$AlertExisting
)

$BundledPython = Join-Path $HOME ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }

$Args = @("monitor.py", "--interval", $Interval)
if ($OpenBrowser) { $Args += "--open-browser" }
if ($Once) { $Args += "--once" }
if ($ShowAll) { $Args += "--show-all" }
if ($AlertExisting) { $Args += "--alert-existing" }

& $Python @Args
