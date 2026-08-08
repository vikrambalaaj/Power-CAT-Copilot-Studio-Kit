<#
.SYNOPSIS
    Deploys and starts the Ask - SuccessFactors MCP Server locally.
#>

$ErrorActionPreference = "Stop"

Write-Host "🚀 Launching Ask - SuccessFactors MCP Server locally..." -ForegroundColor Green

python deploy/regen_manifests.py
python -m successfactors_mcp
