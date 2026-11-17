function Get-File([string[]]$Urls, [string]$Dest) {
    Add-Type -AssemblyName System.Net.Http
    foreach ($u in $Urls) {
        $hostName = ([Uri]$u).Host
        for ($try = 1; $try -le 3; $try++) {
            $client = $null; $in = $null; $out = $null
            try {
                Info "Host: $hostName$(if ($try -gt 1) { " (attempt $try)" })"
                $h = New-Object System.Net.Http.HttpClientHandler
                $h.AllowAutoRedirect = $true
                $client = New-Object System.Net.Http.HttpClient($h)
                $client.Timeout = [TimeSpan]::FromMinutes(40)
                $client.DefaultRequestHeaders.UserAgent.ParseAdd('Mozilla/5.0 (Windows NT 10.0; Win64; x64) ECHOES-Setup/1.0')
                $resp = $client.GetAsync($u, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
                if (-not $resp.IsSuccessStatusCode) { throw "HTTP status $([int]$resp.StatusCode)" }
                $total = $resp.Content.Headers.ContentLength
                $in  = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                $out = [IO.File]::Create($Dest)
                $buf = New-Object byte[] 262144
                [long]$done = 0
                $sw = [Diagnostics.Stopwatch]::StartNew()
                while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
                    $out.Write($buf, 0, $n)
                    $done += $n
                    if ($sw.ElapsedMilliseconds -gt 150) { Show-Bar $done $total; $sw.Restart() }
                }
                Show-Bar $done $total
                [Console]::WriteLine()
                $out.Close(); $out = $null
                if ($done -lt 4096) { throw 'Empty download' }
                if ($total -and $done -lt $total) { throw 'Incomplete download' }
                return $true
            } catch {
                [Console]::WriteLine()
                Warn "Download failed: $($_.Exception.Message)"
                if ($out) { try { $out.Close() } catch {} }
                Remove-Item $Dest -Force -ErrorAction SilentlyContinue
                if ($_.Exception.Message -match 'ответил 4\d\d') { break }
                Start-Sleep -Seconds (2 * $try)
            } finally {
                if ($in) { try { $in.Close() } catch {} }
                if ($client) { try { $client.Dispose() } catch {} }
            }
        }
        # Try the system proxy as a fallback.
        try {
            Info "Trying alternate client: $hostName"
            $wc = New-Object Net.WebClient
            $wc.Headers.Add('User-Agent', 'Mozilla/5.0 ECHOES-Setup/1.0')
            $wc.Proxy = [Net.WebRequest]::GetSystemWebProxy()
            $wc.Proxy.Credentials = [Net.CredentialCache]::DefaultCredentials
            $wc.DownloadFile($u, $Dest)
            if ((Get-Item $Dest).Length -gt 4096) { Ok 'Downloaded'; return $true }
        } catch {
            Warn "Download failed: $($_.Exception.Message)"
            Remove-Item $Dest -Force -ErrorAction SilentlyContinue
        }
    }
    return $false
}

# Each prefetch uses the same mirrors, timeout and retries as Get-File.
function Start-EchoesDownload([string[]]$Urls, [string]$Destination) {
    $worker = [PowerShell]::Create()
    $workerScript = @'
param([string]$DownloadFunction, [string[]]$Urls, [string]$Destination)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
function Info([string]$Text) {}
function Ok([string]$Text) {}
function Warn([string]$Text) { Write-Warning $Text }
function Show-Bar([long]$Done, $Total) {}
Set-Item -Path Function:Get-File -Value ([ScriptBlock]::Create($DownloadFunction))
Get-File $Urls $Destination
'@
    try {
        $downloadFunction = (Get-Command Get-File -CommandType Function).Definition
        $null = $worker.AddScript($workerScript).AddArgument($downloadFunction).AddArgument($Urls).AddArgument($Destination)
        return @{ Worker = $worker; Operation = $worker.BeginInvoke() }
    } catch {
        $worker.Dispose()
        return $null
    }
}

function Receive-EchoesDownload($Download, [string[]]$Urls, [string]$Destination) {
    if ($null -eq $Download) { return (Get-File $Urls $Destination) }
    try {
        $result = $Download.Worker.EndInvoke($Download.Operation)
        if ($result.Count -eq 1 -and $result[0] -eq $true) { return $true }
        foreach ($warning in $Download.Worker.Streams.Warning) { Warn $warning.Message }
        return $false
    } catch {
        Warn $_.Exception.Message
        return $false
    } finally {
        $Download.Worker.Dispose()
    }
}
