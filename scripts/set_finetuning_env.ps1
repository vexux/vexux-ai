# Dot-source this script in each PowerShell session used for QLoRA work:
# . .\scripts\set_finetuning_env.ps1

$ErrorActionPreference = "Stop"

$cacheRoot = "D:\NatWest\huggingface-cache"
$paths = @{
    HF_HOME = $cacheRoot
    HF_HUB_CACHE = Join-Path $cacheRoot "hub"
    HF_XET_CACHE = Join-Path $cacheRoot "xet"
    HF_ASSETS_CACHE = Join-Path $cacheRoot "assets"
    HF_DATASETS_CACHE = Join-Path $cacheRoot "datasets"
    TEMP = "D:\NatWest\huggingface-tmp"
    TMP = "D:\NatWest\huggingface-tmp"
    TORCH_HOME = "D:\NatWest\torch-extensions"
    TORCH_EXTENSIONS_DIR = "D:\NatWest\torch-extensions"
    CUDA_CACHE_PATH = "D:\NatWest\cuda-cache"
    TRITON_CACHE_DIR = "D:\NatWest\triton-cache"
}

foreach ($path in $paths.Values | Select-Object -Unique) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

foreach ($name in $paths.Keys) {
    Set-Item -Path "Env:$name" -Value $paths[$name]
}

Remove-Item Env:TRANSFORMERS_CACHE -ErrorAction SilentlyContinue
