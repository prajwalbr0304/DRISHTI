param(
    [string] $KiroRoot = (Join-Path $env:USERPROFILE ".kiro\sessions"),
    [string] $OutputRoot = (Join-Path ([Environment]::GetFolderPath("Desktop")) "Kiro Sessions"),
    [string] $WorkspaceFilter = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Continue"

function SanitizeFilename {
    param([string] $Name, [int] $MaxLength = 180)

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return $null
    }

    $clean = $Name.Trim()
    $clean = $clean -replace '[\\/:*?"<>|]', '_'
    $clean = $clean -replace '[\x00-\x1F]', ''
    $clean = $clean -replace '\s+', ' '
    $clean = $clean.Trim('. ')

    if ([string]::IsNullOrWhiteSpace($clean)) {
        return $null
    }

    if ($clean.Length -gt $MaxLength) {
        $clean = $clean.Substring(0, $MaxLength).Trim('. ')
    }

    return $clean
}

function Get-ObjectProperty {
    param($Object, [string[]] $Names)

    if ($null -eq $Object -or $null -eq $Object.PSObject) {
        return $null
    }

    $properties = @($Object.PSObject.Properties.Name)
    foreach ($name in $Names) {
        if ($properties -contains $name) {
            return $Object.$name
        }
    }

    return $null
}

function Get-Payload {
    param($Event)

    $payload = Get-ObjectProperty $Event @("payload", "data")
    if ($null -ne $payload -and -not ($payload -is [string])) {
        return $payload
    }

    return $Event
}

function Get-EventType {
    param($Event)

    $payload = Get-Payload $Event
    foreach ($value in @(
        (Get-ObjectProperty $payload @("type", "event", "kind", "name", "role")),
        (Get-ObjectProperty $Event @("type", "event", "kind", "name", "role"))
    )) {
        if (-not [string]::IsNullOrWhiteSpace([string] $value)) {
            return ([string] $value).Trim().ToLowerInvariant()
        }
    }

    return "unknown"
}

function Get-Role {
    param($Event)

    $payload = Get-Payload $Event
    foreach ($value in @(
        (Get-ObjectProperty $payload @("role", "author", "sender", "from")),
        (Get-ObjectProperty $Event @("role", "author", "sender", "from"))
    )) {
        if (-not [string]::IsNullOrWhiteSpace([string] $value)) {
            return ([string] $value).Trim().ToLowerInvariant()
        }
    }

    return $null
}

function ConvertTo-VisibleText {
    param($Value)

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [string]) {
        return $Value
    }

    if ($Value -is [array]) {
        $parts = New-Object System.Collections.Generic.List[string]
        foreach ($item in $Value) {
            $text = ConvertTo-VisibleText $item
            if (-not [string]::IsNullOrEmpty($text)) {
                $parts.Add($text)
            }
        }
        return ($parts -join "`n")
    }

    if ($null -ne $Value.PSObject) {
        foreach ($name in @("text", "content", "markdown", "value", "message", "response", "delta")) {
            $inner = Get-ObjectProperty $Value @($name)
            $text = ConvertTo-VisibleText $inner
            if (-not [string]::IsNullOrEmpty($text)) {
                return $text
            }
        }
    }

    return $null
}

function Get-EventText {
    param($Event)

    $payload = Get-Payload $Event
    foreach ($container in @($payload, $Event)) {
        if ($null -eq $container) {
            continue
        }

        foreach ($name in @("content", "text", "markdown", "delta", "message", "response", "value")) {
            $value = Get-ObjectProperty $container @($name)
            $text = ConvertTo-VisibleText $value
            if (-not [string]::IsNullOrEmpty($text)) {
                return $text
            }
        }
    }

    return $null
}

function Test-InternalType {
    param([string] $Type)

    return $Type -in @(
        "tool_call",
        "tool_result",
        "function_call",
        "function_result",
        "session_metadata",
        "usage_summary",
        "session_event",
        "pending_interaction",
        "interaction_resolved",
        "sub_agent_start",
        "sub_agent_complete",
        "tombstone",
        "metadata",
        "system",
        "developer"
    )
}

function Test-UserType {
    param([string] $Type, [string] $Role)

    return ($Type -in @("user", "human", "session_start", "prompt", "input")) -or ($Role -in @("user", "human"))
}

function Test-AssistantType {
    param([string] $Type, [string] $Role)

    return ($Type -in @("assistant", "model", "assistant_delta", "model_delta", "turn_delta", "message_delta", "response_delta", "response", "output", "completion")) -or ($Role -in @("assistant", "model", "ai"))
}

function Append-AssistantChunk {
    param(
        [ref] $CurrentText,
        [System.Collections.Generic.HashSet[string]] $SeenChunks,
        [string] $Chunk
    )

    if ([string]::IsNullOrEmpty($Chunk)) {
        return
    }

    if ($SeenChunks.Contains($Chunk)) {
        return
    }

    $existing = [string] $CurrentText.Value

    if ([string]::IsNullOrEmpty($existing)) {
        $CurrentText.Value = $Chunk
        $SeenChunks.Add($Chunk) | Out-Null
        return
    }

    if ($Chunk -eq $existing -or $existing.EndsWith($Chunk)) {
        $SeenChunks.Add($Chunk) | Out-Null
        return
    }

    if ($Chunk.StartsWith($existing)) {
        $CurrentText.Value = $Chunk
        $SeenChunks.Add($Chunk) | Out-Null
        return
    }

    $overlap = 0
    $max = [Math]::Min($existing.Length, $Chunk.Length)
    for ($i = $max; $i -gt 0; $i--) {
        if ($existing.Substring($existing.Length - $i, $i) -eq $Chunk.Substring(0, $i)) {
            $overlap = $i
            break
        }
    }

    if ($overlap -gt 0) {
        $CurrentText.Value = $existing + $Chunk.Substring($overlap)
    }
    else {
        $CurrentText.Value = $existing + $Chunk
    }

    $SeenChunks.Add($Chunk) | Out-Null
}

function Add-ConversationBlock {
    param(
        [System.Collections.Generic.List[object]] $Blocks,
        [string] $Role,
        [string] $Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return
    }

    $Blocks.Add([pscustomobject] @{
        Role = $Role
        Text = $Text.Trim("`r", "`n")
    })
}

function Flush-Assistant {
    param(
        [System.Collections.Generic.List[object]] $Blocks,
        [ref] $CurrentAssistant,
        [ref] $SeenChunks
    )

    if (-not [string]::IsNullOrWhiteSpace([string] $CurrentAssistant.Value)) {
        Add-ConversationBlock -Blocks $Blocks -Role "Assistant" -Text ([string] $CurrentAssistant.Value)
    }

    $CurrentAssistant.Value = ""
    $SeenChunks.Value = New-Object 'System.Collections.Generic.HashSet[string]'
}

function Get-ImageExtension {
    param([string] $MimeType, [string] $FileName)

    if (-not [string]::IsNullOrWhiteSpace($FileName)) {
        $extension = [IO.Path]::GetExtension($FileName)
        if (-not [string]::IsNullOrWhiteSpace($extension)) {
            return $extension.TrimStart(".").ToLowerInvariant()
        }
    }

    if ($MimeType -match "png") { return "png" }
    if ($MimeType -match "jpe?g") { return "jpg" }
    if ($MimeType -match "gif") { return "gif" }
    if ($MimeType -match "webp") { return "webp" }
    if ($MimeType -match "bmp") { return "bmp" }
    return "bin"
}

function Save-ImageData {
    param([string] $Data, [string] $Path)

    if ([string]::IsNullOrWhiteSpace($Data)) {
        return $false
    }

    $base64 = $Data
    if ($base64 -match '^data:(?<mime>[^;]+);base64,(?<data>.+)$') {
        $base64 = $Matches.data
    }

    try {
        $bytes = [Convert]::FromBase64String($base64)
        [IO.File]::WriteAllBytes($Path, $bytes)
        return $true
    }
    catch {
        return $false
    }
}

function ExportImages {
    param(
        $Event,
        [string] $ImagesDirectory,
        [string] $SessionName,
        [int] $MessageNumber
    )

    $payload = Get-Payload $Event
    $images = @()

    foreach ($container in @($payload, $Event)) {
        $value = Get-ObjectProperty $container @("images", "image")
        if ($null -ne $value) {
            if ($value -is [array]) { $images += $value } else { $images += @($value) }
        }
    }

    $references = New-Object System.Collections.Generic.List[string]
    if ($images.Count -eq 0) {
        return @()
    }

    New-Item -ItemType Directory -Force -Path $ImagesDirectory | Out-Null
    $imageNumber = 0

    foreach ($image in $images) {
        $imageNumber++

        $data = $null
        $mime = $null
        $name = $null

        if ($image -is [string]) {
            $data = $image
            if ($data -match '^data:(?<mime>[^;]+);base64,') {
                $mime = $Matches.mime
            }
        }
        elseif ($null -ne $image) {
            $data = [string] (Get-ObjectProperty $image @("data", "base64", "content", "bytes"))
            $mime = [string] (Get-ObjectProperty $image @("mimeType", "mime", "type", "mediaType"))
            $name = [string] (Get-ObjectProperty $image @("name", "filename", "fileName", "path"))
        }

        if (-not [string]::IsNullOrWhiteSpace($data)) {
            $ext = Get-ImageExtension -MimeType $mime -FileName $name
            $imageFile = "{0}-{1:000}-{2:000}.{3}" -f $SessionName, $MessageNumber, $imageNumber, $ext
            $imagePath = Join-Path $ImagesDirectory $imageFile
            if (Save-ImageData -Data $data -Path $imagePath) {
                $references.Add("![Image](images/$imageFile)")
            }
            else {
                $references.Add("[Image Attached]")
            }
        }
        else {
            $references.Add("[Image Attached]")
        }
    }

    return @($references)
}

function Get-AttachmentNames {
    param($Event)

    $payload = Get-Payload $Event
    $attachments = @()

    foreach ($container in @($payload, $Event)) {
        foreach ($property in @("attachments", "documents", "files")) {
            $value = Get-ObjectProperty $container @($property)
            if ($null -ne $value) {
                if ($value -is [array]) { $attachments += $value } else { $attachments += @($value) }
            }
        }
    }

    $names = New-Object System.Collections.Generic.List[string]
    foreach ($attachment in $attachments) {
        if ($attachment -is [string]) {
            $names.Add((Split-Path -Leaf $attachment))
        }
        elseif ($null -ne $attachment) {
            $name = [string] (Get-ObjectProperty $attachment @("name", "filename", "fileName", "path", "title"))
            if (-not [string]::IsNullOrWhiteSpace($name)) {
                $names.Add((Split-Path -Leaf $name))
            }
        }
    }

    return @($names)
}

function ReadSession {
    param([string] $Directory, [int] $Index)

    $sessionPath = Join-Path $Directory "session.json"
    $messagesPath = Join-Path $Directory "messages.jsonl"
    $session = $null

    if (Test-Path -LiteralPath $sessionPath) {
        try {
            $session = Get-Content -LiteralPath $sessionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            $session = $null
        }
    }

    $title = $null
    if ($null -ne $session) {
        foreach ($property in @("title", "name", "summary", "description")) {
            $value = Get-ObjectProperty $session @($property)
            if (-not [string]::IsNullOrWhiteSpace([string] $value)) {
                $title = [string] $value
                break
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($title)) {
        $title = "Kiro Session -$Index"
    }

    $created = ""
    $modified = ""

    if (Test-Path -LiteralPath $sessionPath) {
        $created = (Get-Item -LiteralPath $sessionPath).CreationTime.ToString("yyyy-MM-dd HH:mm:ss")
    }

    if (Test-Path -LiteralPath $messagesPath) {
        $modified = (Get-Item -LiteralPath $messagesPath).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    }

    return [pscustomobject] @{
        Title = $title
        Directory = $Directory
        SessionPath = $sessionPath
        MessagesPath = $messagesPath
        Created = $created
        Modified = $modified
    }
}

function Test-SessionMatchesWorkspace {
    param(
        [string] $Directory,
        [string] $WorkspaceFilter
    )

    if ([string]::IsNullOrWhiteSpace($WorkspaceFilter)) {
        return $true
    }

    $sessionPath = Join-Path $Directory "session.json"
    if (-not (Test-Path -LiteralPath $sessionPath)) {
        return $false
    }

    try {
        $session = Get-Content -LiteralPath $sessionPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $false
    }

    $wanted = [IO.Path]::GetFullPath($WorkspaceFilter).TrimEnd('\').ToLowerInvariant()
    $paths = @(Get-ObjectProperty $session @("workspacePaths", "workspacePath", "cwd", "projectRoot", "folder"))

    foreach ($path in $paths) {
        if ([string]::IsNullOrWhiteSpace([string] $path)) {
            continue
        }

        try {
            $actual = [IO.Path]::GetFullPath([string] $path).TrimEnd('\').ToLowerInvariant()
            if ($actual -eq $wanted) {
                return $true
            }
        }
        catch {
            if (([string] $path).ToLowerInvariant().Contains($wanted)) {
                return $true
            }
        }
    }

    return $false
}

function InspectMessages {
    param([string] $MessagesPath)

    $types = @{}
    if (-not (Test-Path -LiteralPath $MessagesPath)) {
        return $types
    }

    $reader = New-Object IO.StreamReader($MessagesPath, [Text.Encoding]::UTF8, $true)
    $lineNumber = 0
    try {
        while (-not $reader.EndOfStream -and $lineNumber -lt 300) {
            $lineNumber++
            $line = $reader.ReadLine()
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }

            try {
                $event = $line | ConvertFrom-Json
                $type = Get-EventType $event
                if (-not $types.ContainsKey($type)) {
                    $types[$type] = 0
                }
                $types[$type]++
            }
            catch {
                if (-not $types.ContainsKey("malformed")) {
                    $types["malformed"] = 0
                }
                $types["malformed"]++
            }
        }
    }
    finally {
        $reader.Dispose()
    }

    return $types
}

function ParseMessages {
    param(
        [string] $MessagesPath,
        [string] $ImagesDirectory,
        [string] $SessionName,
        [hashtable] $Stats
    )

    $blocks = New-Object System.Collections.Generic.List[object]
    $currentAssistant = ""
    $seenChunks = New-Object 'System.Collections.Generic.HashSet[string]'
    $visibleMessageNumber = 0

    $reader = New-Object IO.StreamReader($MessagesPath, [Text.Encoding]::UTF8, $true)
    try {
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }

            try {
                $event = $line | ConvertFrom-Json
            }
            catch {
                $Stats.Errors++
                continue
            }

            $type = Get-EventType $event
            $role = Get-Role $event

            if ($type -eq "turn_start" -or $type -eq "turn_end") {
                Flush-Assistant -Blocks $blocks -CurrentAssistant ([ref] $currentAssistant) -SeenChunks ([ref] $seenChunks)
                continue
            }

            if (Test-InternalType $type) {
                continue
            }

            if (Test-UserType -Type $type -Role $role) {
                Flush-Assistant -Blocks $blocks -CurrentAssistant ([ref] $currentAssistant) -SeenChunks ([ref] $seenChunks)
                $visibleMessageNumber++

                $parts = New-Object System.Collections.Generic.List[string]
                $text = Get-EventText $event
                if (-not [string]::IsNullOrWhiteSpace($text)) {
                    $parts.Add($text.Trim("`r", "`n"))
                }

                foreach ($imageRef in @(ExportImages -Event $event -ImagesDirectory $ImagesDirectory -SessionName $SessionName -MessageNumber $visibleMessageNumber)) {
                    $parts.Add($imageRef)
                }

                $attachments = @(Get-AttachmentNames $event)
                if ($attachments.Count -gt 0) {
                    $attachmentLines = New-Object System.Collections.Generic.List[string]
                    $attachmentLines.Add("[Attachment]")
                    foreach ($attachment in $attachments) {
                        if (-not [string]::IsNullOrWhiteSpace($attachment)) {
                            $attachmentLines.Add($attachment)
                        }
                    }
                    $parts.Add(($attachmentLines -join "`n"))
                }

                if ($parts.Count -gt 0) {
                    Add-ConversationBlock -Blocks $blocks -Role "User" -Text ($parts -join "`n`n")
                }

                continue
            }

            if (Test-AssistantType -Type $type -Role $role) {
                $payload = Get-Payload $event
                $operationType = [string] (Get-ObjectProperty $payload @("operationType", "operation", "op"))
                if ($operationType -match '^(metadata|reasoning_signature|tool|hidden|system)$') {
                    continue
                }

                $text = Get-EventText $event
                Append-AssistantChunk -CurrentText ([ref] $currentAssistant) -SeenChunks $seenChunks -Chunk $text
            }
        }

        Flush-Assistant -Blocks $blocks -CurrentAssistant ([ref] $currentAssistant) -SeenChunks ([ref] $seenChunks)
    }
    finally {
        $reader.Dispose()
    }

    return ,$blocks
}

function WriteMarkdown {
    param($Session, [System.Collections.Generic.List[object]] $Blocks, [string] $Path)

    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    $writer = New-Object IO.StreamWriter($Path, $false, $utf8NoBom)
    try {
        $writer.WriteLine("# {0}" -f $Session.Title)
        $writer.WriteLine()
        $writer.WriteLine("Created: {0}" -f $Session.Created)
        $writer.WriteLine("Last Modified: {0}" -f $Session.Modified)
        $writer.WriteLine()
        $writer.WriteLine("---")
        $writer.WriteLine()

        foreach ($block in $Blocks) {
            if ([string]::IsNullOrWhiteSpace([string] $block.Text)) {
                continue
            }

            $writer.WriteLine("## {0}" -f $block.Role)
            $writer.WriteLine()
            $writer.WriteLine(([string] $block.Text).Trim("`r", "`n"))
            $writer.WriteLine()
        }
    }
    finally {
        $writer.Dispose()
    }
}

function Main {
    $stats = @{
        Exported = 0
        Skipped = 0
        Errors = 0
    }

    if (-not (Test-Path -LiteralPath $KiroRoot)) {
        throw "Kiro sessions folder not found: $KiroRoot"
    }

    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    $imagesDirectory = Join-Path $OutputRoot "images"
    New-Item -ItemType Directory -Force -Path $imagesDirectory | Out-Null

    $sessionDirs = Get-ChildItem -LiteralPath $KiroRoot -Recurse -Force -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "messages.jsonl")) -and
            (Test-SessionMatchesWorkspace -Directory $_.FullName -WorkspaceFilter $WorkspaceFilter)
        } |
        Sort-Object FullName

    $exportIndex = 0
    foreach ($dir in $sessionDirs) {
        $candidateNumber = $exportIndex + 1
        $session = ReadSession -Directory $dir.FullName -Index $candidateNumber

        Write-Host "Exporting:"
        Write-Host $session.Title

        if (-not (Test-Path -LiteralPath $session.MessagesPath)) {
            $stats.Skipped++
            continue
        }

        $messagesItem = Get-Item -LiteralPath $session.MessagesPath
        if ($messagesItem.Length -eq 0) {
            $stats.Skipped++
            continue
        }

        try {
            $null = InspectMessages -MessagesPath $session.MessagesPath
            $exportIndex++
            $forcedBaseName = "Kiro Session -$exportIndex"
            $safeName = SanitizeFilename $forcedBaseName
            $outputPath = Join-Path $OutputRoot ($safeName + ".md")

            $blocks = ParseMessages -MessagesPath $session.MessagesPath -ImagesDirectory $imagesDirectory -SessionName $safeName -Stats $stats
            if ($blocks.Count -eq 0) {
                $stats.Skipped++
                Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
                continue
            }

            $session.Title = $forcedBaseName
            WriteMarkdown -Session $session -Blocks $blocks -Path $outputPath
            $stats.Exported++
        }
        catch {
            $stats.Errors++
            Write-Warning ("Failed to export {0}: {1}" -f $dir.FullName, $_.Exception.Message)
        }
    }

    Write-Host ""
    Write-Host "Sessions exported: $($stats.Exported)"
    Write-Host "Skipped: $($stats.Skipped)"
    Write-Host "Errors: $($stats.Errors)"
    Write-Host "Output:"
    Write-Host $OutputRoot
}

Main
