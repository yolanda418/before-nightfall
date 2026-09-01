# -*- coding: utf-8 -*-
# Chapter quality checker for Tianhei Zhiqian (PS 5.1 compatible).
# Migrated from open-souls check_ch82x.py, adapted to v3.1 rules.
#
# Usage:
#     powershell -ExecutionPolicy Bypass -File tools\check_chapter_quality.ps1
#     powershell ... check_chapter_quality.ps1 -Chapter 5
#     powershell ... check_chapter_quality.ps1 -Json

[CmdletBinding()]
param(
    [string]$Chapter = "",
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---- Path resolution ----
$scriptFullPath = $MyInvocation.MyCommand.Path
if (-not $scriptFullPath) { $scriptFullPath = $PSCommandPath }
$scriptRoot = [System.IO.Path]::GetDirectoryName($scriptFullPath)
$root = [System.IO.Path]::GetDirectoryName($scriptRoot)
$chapDir = [System.IO.Path]::Combine($root, 'chapters')

# ---- v3.1 thresholds ----
$V3Min = 1800
$V3Max = 2200

# ---- Helper: build string from codepoints ----
function C([int[]]$cp) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($c in $cp) { [void]$sb.Append([char]$c) }
    return $sb.ToString()
}

# ---- Pure-char counter ----
function Count-Pure([string]$t) {
    $n = 0
    foreach ($c in $t.ToCharArray()) {
        if ($c -match '^[\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]$') { $n++ }
    }
    return $n
}

# ---- Body extraction ----
function Get-Body([string]$text) {
    $lines = $text -split "`r?`n"
    $start = -1
    $end = $lines.Length
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

# ---- CJK punctuation class ----
$NOT_PUNCT = '[^' + [char]0x3002 + [char]0xFF01 + [char]0xFF1F + ',!?;' + [char]0x0A + [char]0x0D + ']'
$emdash = [char]0x2014 + [char]0x2014

# ---- Pattern definitions (CJK chars built via codepoints) ----
$p_ai_connector = (C @(0x53EA,0x898B)) + '|' + (C @(0x5C31,0x5728,0x8FD9,0x65F6)) + '|' + (C @(0x7247,0x523B,0x540E)) + '|' + (C @(0x968F,0x5373)) + '|' + (C @(0x4E8E,0x662F)) + '|' + (C @(0x56E0,0x6B64)) + '|' + (C @(0x4E0D,0x7531,0x5F97)) + '|' + (C @(0x4E0D,0x7981)) + '|' + (C @(0x4F3C,0x4E4E)) + '|' + (C @(0x4F3C,0x4F3B)) + '|' + (C @(0x597D,0x50CF))
$p_ai_adv = (C @(0x975E,0x5E38)) + '|' + (C @(0x6781,0x5176)) + '|' + (C @(0x683C,0x5916)) + '|' + (C @(0x7A0D,0x7A0D)) + '|' + (C @(0x9ED8,0x9ED8))
$p_ai_highfreq = (C @(0x773C,0x775B)) + '|' + (C @(0x5507,0x89D2)) + '|' + (C @(0x8EAB,0x5F62)) + '|' + (C @(0x51B1,0x7136))
$p_neg_contrast = (C @(0x6CA1,0x6709)) + $NOT_PUNCT + '{0,15}' + (C @(0x6CA1,0x6709)) + '|' + (C @(0x4E0D,0x662F)) + $NOT_PUNCT + '{0,15}' + (C @(0x800C,0x662F)) + '|' + (C @(0x5E76,0x975E)) + $NOT_PUNCT + '{0,15}' + (C @(0x800C,0x662F)) + '|' + (C @(0x6CA1,0x6709)) + $NOT_PUNCT + '{0,15}' + (C @(0x53EA,0x662F))
$p_weak_trans = (C @(0x8C79,0x7136)) + $NOT_PUNCT + '{0,15}' + (C @(0x4F46,0x662F)) + '|' + (C @(0x5C3D,0x7BA1)) + $NOT_PUNCT + '{0,15}' + (C @(0x5374)) + '|' + (C @(0x751A,0x81F3)) + $NOT_PUNCT + '{0,15}' + (C @(0x6CA1,0x6709))
$p_god_view = (C @(0x8BFB,0x8005,0x4EEC,0x90FD,0x77E5,0x9053)) + '|' + (C @(0x6240,0x6709,0x4EBA,0x90FD,0x77E5,0x9053)) + '|' + (C @(0x4E8B,0x5B9E,0x4E0A)) + '|' + (C @(0x539F,0x6765)) + '[' + [char]0x4E00 + '-' + [char]0x9FFF + ']{0,8}(?:' + (C @(0x4E00,0x76F4)) + '|' + (C @(0x65E9,0x5C31)) + '|' + (C @(0x4ECE,0x6765)) + ')'
$p_banned = (C @(0x7F6A,0x5DF1,0x4FA7,0x5199)) + '|' + (C @(0x7B7E,0x540D,0x884C,0x4E3A)) + '|' + (C @(0x573A,0x4F9D,0x5B58,0x6027)) + '|' + (C @(0x9632,0x5FA1,0x6027,0x4F24,0x4F24)) + '|' + (C @(0x79FB,0x60C5)) + '|Overkill'
$p_template = '[' + [char]0x4E00 + '-' + [char]0x9FFF + ']{1,4}[' + [char]0x4E00 + '-' + [char]0x9FFF + ']{0,2}?(?:' + (C @(0x5730,0x8BF4)) + '|' + (C @(0x8BF4,0x7740)) + '|' + (C @(0x770B,0x5411)) + '|' + (C @(0x770B,0x7740)) + '|' + (C @(0x671B,0x7740)) + '|' + (C @(0x8D70,0x8FC7,0x53BB)) + '|' + (C @(0x95EE,0x9053)) + '|' + (C @(0x95EE)) + ')'
$dialogueOnlyLine = '^\s*[' + [char]0x201C + [char]0x300C + '"''][^' + [char]0x201D + [char]0x300D + '"''\r\n' + ']{1,80}[' + [char]0x201D + [char]0x300D + '"''][' + [char]0x3002 + ',]?\s*$'

# ---- Main loop ----
$pattern = 'Chapter_*.md'
if ($Chapter) {
    $pattern = "Chapter_{0:D2}.md" -f [int]$Chapter
}
$files = @()
try {
    $files = [System.IO.Directory]::GetFiles($chapDir, $pattern) | Sort-Object
} catch {
    Write-Host "ERROR listing chapters: $($_.Exception.Message)"
    exit 1
}
if (-not $files -or $files.Count -eq 0) {
    Write-Host "No chapter files found for pattern: $pattern"
    exit 1
}

$results = @()

foreach ($f in $files) {
    $text = [System.IO.File]::ReadAllText($f, [System.Text.Encoding]::UTF8)
    $body = Get-Body $text
    $fname = Split-Path -Leaf $f
    $pure = Count-Pure $body

    $aiConnectorCount = ([regex]::Matches($body, $p_ai_connector)).Count
    $aiAdvCount = ([regex]::Matches($body, $p_ai_adv)).Count
    $aiHighfreqCount = ([regex]::Matches($body, $p_ai_highfreq)).Count
    $negContrastCount = ([regex]::Matches($body, $p_neg_contrast)).Count
    $weakTransCount = ([regex]::Matches($body, $p_weak_trans)).Count
    $godViewCount = ([regex]::Matches($body, $p_god_view)).Count
    $bannedCount = ([regex]::Matches($body, $p_banned)).Count
    $templateCount = ([regex]::Matches($body, $p_template)).Count

    $paragraphs = $body -split "`n`n"
    $dashMax = 0
    foreach ($para in $paragraphs) {
        $d = ([regex]::Matches($para, [regex]::Escape($emdash))).Count
        if ($d -gt $dashMax) { $dashMax = $d }
    }

    $bodyLines = $body -split "`r?`n"
    $dialogueOnlyCount = 0
    foreach ($bl in $bodyLines) {
        if ([regex]::IsMatch($bl, $dialogueOnlyLine)) { $dialogueOnlyCount++ }
    }

    $charStatus = "OK"
    if ($pure -lt $V3Min) { $charStatus = "UNDER" }
    elseif ($pure -gt $V3Max) { $charStatus = "OVER" }

    $result = [PSCustomObject]@{
        file = $fname
        pure_chars = $pure
        char_status = $charStatus
        ai_connector = $aiConnectorCount
        ai_filler_adv = $aiAdvCount
        ai_highfreq = $aiHighfreqCount
        template_verb = $templateCount
        neg_contrast = $negContrastCount
        weak_trans = $weakTransCount
        god_view = $godViewCount
        banned_terms = $bannedCount
        dash_max = $dashMax
        dialogue_only = $dialogueOnlyCount
    }
    $results += $result
}

# ---- Output ----
if ($Json) {
    $results | ConvertTo-Json -Depth 3
} else {
    foreach ($r in $results) {
        $verdict = "OK "
        if ($r.char_status -ne "OK") { $verdict = "OUT" }
        if ($r.god_view -gt 0) { $verdict = "FAIL" }
        if ($r.neg_contrast -gt 0) { $verdict = "FAIL" }

        Write-Host ("[{0}] {1,-18}  pure={2} ({3})" -f $verdict, $r.file, $r.pure_chars, $r.char_status)
        if ($r.char_status -ne "OK") {
            Write-Host ("    CHARS: {0} chars, target [{1}, {2}]" -f $r.pure_chars, $V3Min, $V3Max)
        }
        $details = @()
        if ($r.ai_connector -gt 0)   { $details += "AI_connector=$($r.ai_connector)" }
        if ($r.ai_filler_adv -gt 0)  { $details += "AI_filler_adv=$($r.ai_filler_adv)" }
        if ($r.ai_highfreq -gt 0)    { $details += "AI_highfreq=$($r.ai_highfreq)" }
        if ($r.template_verb -gt 0)   { $details += "template_verb=$($r.template_verb)" }
        if ($r.neg_contrast -gt 0)   { $details += "neg_contrast=$($r.neg_contrast)" }
        if ($r.weak_trans -gt 0)     { $details += "weak_trans=$($r.weak_trans)" }
        if ($r.god_view -gt 0)       { $details += "god_view=$($r.god_view)" }
        if ($r.banned_terms -gt 0)   { $details += "banned_terms=$($r.banned_terms)" }
        if ($r.dash_max -ge 5)       { $details += "dash_overload=$($r.dash_max)" }
        if ($r.dialogue_only -gt 0)  { $details += "dialogue_only=$($r.dialogue_only)" }
        if ($details.Count -gt 0) {
            Write-Host ("    HITS: " + ($details -join ", "))
        }
        Write-Host ""
    }
    Write-Host ("Total: {0} chapters scanned" -f $results.Count)
}
