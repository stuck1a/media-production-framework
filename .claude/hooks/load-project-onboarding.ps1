$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$developerGuide = Join-Path $projectRoot "docs\developer-guide.md"

if (-not (Test-Path -LiteralPath $developerGuide -PathType Leaf)) {
    throw "Required onboarding entry point not found: docs/developer-guide.md"
}

function Get-RelativeProjectPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $rootPath = $projectRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) +
        [System.IO.Path]::DirectorySeparatorChar
    $rootUri = [System.Uri]::new($rootPath)
    $pathUri = [System.Uri]::new($Path)
    $relativeUri = $rootUri.MakeRelativeUri($pathUri).ToString()

    return [System.Uri]::UnescapeDataString($relativeUri)
}

function Add-OnboardingFile {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[string]] $Files,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.HashSet[string]] $Seen,

        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $resolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue).Path
    if ($null -eq $resolvedPath) {
        return
    }

    if ((Test-Path -LiteralPath $resolvedPath -PathType Leaf) -and $Seen.Add($resolvedPath)) {
        $Files.Add($resolvedPath)
    }
}

$onboardingFiles = [System.Collections.Generic.List[string]]::new()
$seenFiles = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)

Add-OnboardingFile -Files $onboardingFiles -Seen $seenFiles -Path $developerGuide

$developerGuideContent = Get-Content -LiteralPath $developerGuide -Raw
$pathMatches = [regex]::Matches($developerGuideContent, '`([^`]+)`')

foreach ($match in $pathMatches) {
    $reference = $match.Groups[1].Value.Trim()
    $isProjectDocument = $reference.StartsWith("docs/") -or $reference -eq "CONTRIBUTING.md"

    if (-not $isProjectDocument) {
        continue
    }

    if ($reference.EndsWith("*")) {
        $directoryReference = $reference.Substring(0, $reference.Length - 1).TrimEnd("/")
        $directoryPath = Join-Path $projectRoot $directoryReference
        if (Test-Path -LiteralPath $directoryPath -PathType Container) {
            Get-ChildItem -LiteralPath $directoryPath -Filter "*.md" -File |
                Sort-Object -Property Name |
                ForEach-Object {
                    Add-OnboardingFile -Files $onboardingFiles -Seen $seenFiles -Path $_.FullName
                }
        }
        continue
    }

    $projectPath = Join-Path $projectRoot $reference

    if (Test-Path -LiteralPath $projectPath -PathType Container) {
        Get-ChildItem -LiteralPath $projectPath -Filter "*.md" -File |
            Sort-Object -Property Name |
            ForEach-Object {
                Add-OnboardingFile -Files $onboardingFiles -Seen $seenFiles -Path $_.FullName
            }
        continue
    }

    Add-OnboardingFile -Files $onboardingFiles -Seen $seenFiles -Path $projectPath
}

$loadedFiles = $onboardingFiles | ForEach-Object { Get-RelativeProjectPath -Path $_ }
$sections = [System.Collections.Generic.List[string]]::new()

foreach ($file in $onboardingFiles) {
    $relativePath = Get-RelativeProjectPath -Path $file
    $content = Get-Content -LiteralPath $file -Raw
    $sections.Add("## File: $relativePath`n`n$content")
}

$additionalContext = @"
Media Production Framework project onboarding was loaded automatically.

The authoritative onboarding entry point is docs/developer-guide.md.
The hook read that file first, then read the project documents referenced there in first-mention order.

Loaded files:
$($loadedFiles | ForEach-Object { "- $_" } | Out-String)

Use docs/roadmap.md to determine the current milestone before continuing project work.

$($sections -join "`n`n---`n`n")
"@

@{
    hookSpecificOutput = @{
        hookEventName = "SessionStart"
        additionalContext = $additionalContext
    }
} | ConvertTo-Json -Depth 5
