# NYC Taxi Demand Platform - Application Launcher

$nodePath = "$env:LOCALAPPDATA\Programs\cursor\resources\app\resources\helpers\node.exe"

if (Test-Path $nodePath) {
    Write-Host "Starting NYC Taxi Demand App using $nodePath..."
    & $nodePath app/server.js
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "Starting NYC Taxi Demand App using system node..."
    node app/server.js
} else {
    Write-Error "Error: Node.js was not found on this system."
}
