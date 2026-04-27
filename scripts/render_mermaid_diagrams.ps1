$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$diagramDir = Join-Path $root "docs\diagrams\mermaid"
$outputDir = Join-Path $root "output\figures"
$targetScale = 5

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$files = Get-ChildItem -Path $diagramDir -Filter *.mmd | Sort-Object Name
if (-not $files) {
  throw "No Mermaid files found in $diagramDir"
}

foreach ($file in $files) {
  $name = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
  $pngPath = Join-Path $outputDir ($name + ".png")
  $svgPath = Join-Path $outputDir ($name + ".svg")

  npx -y @mermaid-js/mermaid-cli@10.9.1 -i $file.FullName -o $pngPath -b transparent -s $targetScale
  npx -y @mermaid-js/mermaid-cli@10.9.1 -i $file.FullName -o $svgPath -b transparent

  @"
from PIL import Image

png_path = r"$pngPath"
img = Image.open(png_path)
img.save(png_path, dpi=(600, 600))
"@ | python -
}

Write-Output "Rendered $($files.Count) Mermaid diagrams to $outputDir at 600 DPI"
