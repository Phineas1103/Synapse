$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$version = "1.0.0"
$installerName = "Synapse_Setup_v$version.exe"
$installerPath = Join-Path $projectRoot "installer_output\$installerName"
$releaseRoot = Join-Path $projectRoot "release\web-download"
$downloadsDir = Join-Path $releaseRoot "downloads"
$baseUrl = if ($env:SYNAPSE_DOWNLOAD_BASE_URL) {
  $env:SYNAPSE_DOWNLOAD_BASE_URL.TrimEnd("/") + "/"
} else {
  "http://124.221.179.140:8788/downloads/synapse/"
}

if (-not (Test-Path -LiteralPath $installerPath)) {
  throw "Installer not found: $installerPath. Please build installer first."
}

if (Test-Path -LiteralPath $releaseRoot) {
  Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}

New-Item -ItemType Directory -Force $downloadsDir | Out-Null
$releaseInstaller = Join-Path $downloadsDir $installerName
Copy-Item -LiteralPath $installerPath -Destination $releaseInstaller -Force

$file = Get-Item -LiteralPath $releaseInstaller
$hash = (Get-FileHash -LiteralPath $releaseInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
$generatedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
$downloadUrl = $baseUrl + "downloads/" + $installerName
$sizeMb = [Math]::Round($file.Length / 1MB, 1)

$latest = [ordered]@{
  app = "Synapse"
  version = $version
  filename = $installerName
  size = $file.Length
  sha256 = $hash
  download_url = $downloadUrl
  generated_at = $generatedAt
}
$latest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $releaseRoot "latest.json") -Encoding UTF8

$indexHtml = @"
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Synapse 下载</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #f7f3ff; background: #07050d; }
    main { width: min(520px, calc(100vw - 40px)); padding: 36px; border: 1px solid rgba(255,255,255,.12); border-radius: 18px; background: linear-gradient(145deg, rgba(44,31,68,.82), rgba(14,13,24,.95)); box-shadow: 0 24px 80px rgba(0,0,0,.45); }
    h1 { margin: 0 0 8px; font-size: 34px; }
    p { color: #c9c0d8; line-height: 1.7; }
    a.button { display: block; margin: 26px 0 18px; padding: 16px 18px; border-radius: 12px; color: #fff; text-align: center; text-decoration: none; font-weight: 700; background: linear-gradient(135deg, #6f86e8, #8b5ac6); }
    .meta { font-size: 13px; color: #9e94ad; word-break: break-all; }
  </style>
</head>
<body>
  <main>
    <h1>Synapse</h1>
    <p>AI 漫剧创作平台 Windows 安装包。下载后双击安装，可选择安装路径，并默认创建桌面快捷方式。</p>
    <a class="button" href="downloads/$installerName">下载安装包</a>
    <div class="meta">版本：$version</div>
    <div class="meta">大小：$sizeMb MB</div>
    <div class="meta">SHA256：$hash</div>
    <div class="meta">生成时间：$generatedAt</div>
  </main>
</body>
</html>
"@
Set-Content -LiteralPath (Join-Path $releaseRoot "index.html") -Value $indexHtml -Encoding UTF8

$readme = @"
# Synapse web download release

Upload all files under release\web-download to your static server.

Recommended server path:

/downloads/synapse/

Download page:

http://124.221.179.140:8788/downloads/synapse/index.html

Direct installer:

http://124.221.179.140:8788/downloads/synapse/downloads/${installerName}

Files:

- index.html: public download page
- latest.json: version, size, sha256 and download URL
- downloads/${installerName}: full Windows installer
"@
Set-Content -LiteralPath (Join-Path $releaseRoot "README.md") -Value $readme -Encoding UTF8

Get-ChildItem -LiteralPath $releaseRoot -Recurse -File |
  Select-Object FullName, Length, LastWriteTime

Write-Host "Download page: $($baseUrl)index.html"
Write-Host "Installer URL: $downloadUrl"
