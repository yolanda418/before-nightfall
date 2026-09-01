# 天黑之前 · Chapter stats (v3.1 · 重写版)
#
# 移植自原 tools/chapter_stats.ps1（2026/8/31 之前的 GBK 字节拼路径版），
# 已按 v3.1 标准（1800-2200 字）重写：
#   · 去 GBK 字节 hack（直接用 -LiteralPath 接受 UTF-8 中文路径）
#   · 阈值改为 v3.1 [1800, 2200]，中位 2000
#   · 标签中文化外部化为 tools/_stats_labels.txt（UTF-8, no BOM）
#   · 加 -Chapter 参数：只扫指定章节
#   · 加 -Json 输出：便于被 Python/CI 调用
#
# Counts（按 .clinerules 4.2 节网文统计口径）：
#   (1) Pure chars  = CJK ideographs + ASCII letters + ASCII digits
#                     (no punctuation, no whitespace, no newline, no md symbols)
#   (2) WithPunctNoNL = (1) + all punct + spaces/tabs (no \r \n)
#   (3) WithNewline  = (2) + line terminators
#   v3.1 (2026/8/31) target: ① ∈ [1800, 2200]; widen ∈ [1600, 2400]
#
# Body extraction: from "## <CJK: er>" header line up to next "---" separator.
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\chapter_stats.ps1              # 扫全部
#   powershell ... chapter_stats.ps1 -Chapter 5                                    # 只扫第 5 章
#   powershell ... chapter_stats.ps1 -Json                                        # 输出 JSON

[CmdletBinding()]
param(
    [string]$Chapter = "",
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 用 [System.IO.Path] 静态方法避开 PS 5.1 中文路径 bug
# 不依赖 $PSCommandPath 的 Split-Path
$scriptFullPath = $MyInvocation.MyCommand.Path
if (-not $scriptFullPath) { $scriptFullPath = $PSCommandPath }
$scriptRoot = [System.IO.Path]::GetDirectoryName($scriptFullPath)
$root = [System.IO.Path]::GetDirectoryName($scriptRoot)
$chapDir = [System.IO.Path]::Combine($root, 'chapters')
$outFile = [System.IO.Path]::Combine($scriptRoot, '_chapter_stats.txt')
$csvFile = [System.IO.Path]::Combine($scriptRoot, '_chapter_stats.csv')

# ---- v3.1 阈值常量 ----
$script:V3Min = 1800
$script:V3Max = 2200
$script:WidenLow = 1600
$script:WidenHigh = 2400

# 加载中文标签（UTF-8，无 BOM）
$labelsPath = Join-Path $scriptRoot '_stats_labels.txt'
if (Test-Path -LiteralPath $labelsPath) {
    $labels = Get-Content -LiteralPath $labelsPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    # 后备：硬编码中文（避免外部文件丢失时崩溃）
    $labels = @{
        chapter   = 'Chapter'
        header    = 'chapter  pure(1)  punct(2)  withNL(3)  note'
        sep       = ('-' * 70)
        sum       = 'TOTAL'
        ok_v3     = 'OK v3.1 1800-2200'
        ok_widen  = 'OK widen v3.1 1600-2400'
        out_v3    = 'OUT v3.1 (delta='
        not_classified = 'OUT v3.1 (NOT-CLASSIFIED)'
        file_header = "Chapter              Pure(1)  Punct(2)  WithNL(3)  | Note"
    }
}

# ---- 字数统计函数（沿用原版正则） ----
$pureRe = '^[\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]$'
$nlRe   = '^[\r\n]$'

function Count-Pure([string]$t) {
    $n = 0
    foreach ($c in $t.ToCharArray()) {
        if ($c -match $pureRe) { $n++ }
    }
    return $n
}

function Count-PunctNoNL([string]$t) {
    $n = 0
    foreach ($c in $t.ToCharArray()) {
        if ($c -match $nlRe) { continue }
        $n++
    }
    return $n
}

function Count-WithNL([string]$t) { return $t.Length }

# ---- 正文字段提取 ----
function Extract-Body([string]$text) {
    $lines = $text -split "`r?`n"
    $start = -1
    $end   = $lines.Length
    $prefix = '## ' + [char]0x4E8C
    for ($i = 0; $i -lt $lines.Length; $i++) {
        $t = $lines[$i].Trim()
        if ($start -lt 0 -and $t.StartsWith($prefix)) {
            $start = $i + 1
            continue
        }
        if ($start -ge 0 -and $t -eq '---') {
            $end = $i
            break
        }
    }
    if ($start -lt 0) { return $text }
    if ($end -le $start) { return '' }
    return ($lines[$start..($end - 1)] -join "`n")
}

# ---- v3.1 判定 ----
function Classify-Chars([int]$p) {
    if (($p -ge $script:V3Min) -and ($p -le $script:V3Max)) {
        return $labels.ok_v3
    }
    if (($p -ge $script:WidenLow) -and ($p -le $script:WidenHigh)) {
        return $labels.ok_widen
    }
    $d = $p - ($script:V3Min + $script:V3Max) / 2   # 中位 2000
    return "$($labels.out_v3)$d)"
}

# ---- 主流程 ----
$pattern = 'Chapter_*.md'
if ($Chapter) {
    $pattern = "Chapter_{0:D2}.md" -f [int]$Chapter
}

# 用 .NET 静态方法代替 Get-ChildItem（避开 PS 5.1 中文路径 bug）
$files = @()
try {
    $files = [System.IO.Directory]::GetFiles($chapDir, $pattern) | Sort-Object
} catch {
    Write-Host ("ERROR listing chapters: " + $_.Exception.Message)
    exit 1
}
if (-not $files -or $files.Count -eq 0) {
    Write-Host ("No chapter files found for pattern: " + $pattern)
    exit 1
}

$out = New-Object System.Collections.Generic.List[string]
$csv = New-Object System.Collections.Generic.List[string]
$csv.Add('file,pure_chars,with_punct_no_nl,with_newline_total,verdict')
$out.Add($labels.file_header)
$out.Add(('-' * 78))

$sumP = 0; $sumA = 0; $sumB = 0
$results = @()

foreach ($f in $files) {
    # 用 .NET 静态方法代替 Get-Content（PS 5.1 中文路径兼容）
    $raw = [System.IO.File]::ReadAllText($f, [System.Text.Encoding]::UTF8)
    $body = Extract-Body $raw
    $p = Count-Pure $body
    $a = Count-PunctNoNL $body
    $b = Count-WithNL $body
    $sumP += $p; $sumA += $a; $sumB += $b

    $verdict = Classify-Chars $p
    $fname = Split-Path -Leaf $f
    $row = $fname.PadRight(18) + '  ' + ($p.ToString()).PadLeft(8) + '  ' + ($a.ToString()).PadLeft(8) + '  ' + ($b.ToString()).PadLeft(8) + '  | ' + $verdict
    $out.Add($row)
    $csv.Add(($fname + ',' + $p + ',' + $a + ',' + $b + ',' + $verdict))
    $results += [PSCustomObject]@{
        file = $f.Name
        pure = $p
        punct = $a
        withNL = $b
        verdict = $verdict
    }
}
$out.Add(('-' * 78))
$out.Add(('TOTAL                ' + $sumP.ToString().PadLeft(8) + '     ' + $sumA.ToString().PadLeft(8) + '     ' + $sumB.ToString().PadLeft(8)))

if (-not $Json) {
    # 用 .NET 静态方法代替 Out-File（PS 5.1 中文路径兼容）
    [System.IO.File]::WriteAllLines($outFile, $out, [System.Text.Encoding]::UTF8)
    [System.IO.File]::WriteAllLines($csvFile, $csv, [System.Text.Encoding]::UTF8)
    $out | ForEach-Object { Write-Host $_ }
} else {
    # JSON 模式：直接输出到 stdout（便于管道）
    $results | ConvertTo-Json -Depth 3
}
