param(
    [string] $SourceRoot = (Join-Path ([Environment]::GetFolderPath("Desktop")) "DRISHTI_KIRO_SESSIONS"),
    [string] $OutputRoot = (Join-Path ([Environment]::GetFolderPath("Desktop")) "DRISHTI_KIRO_SESSIONS_HTML")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

function Encode-Html {
    param([AllowNull()][string] $Text)

    if ($null -eq $Text) {
        return ""
    }

    return [System.Net.WebUtility]::HtmlEncode($Text)
}

function Convert-InlineMarkdown {
    param([AllowNull()][string] $Text)

    $encoded = Encode-Html $Text
    $encoded = [regex]::Replace($encoded, '!\[([^\]]*)\]\(([^)]+)\)', '<img class="attached-image" alt="$1" src="$2">')
    $encoded = [regex]::Replace($encoded, '\[([^\]]+)\]\((https?://[^)]+)\)', '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    $encoded = [regex]::Replace($encoded, '`([^`]+)`', '<code>$1</code>')
    $encoded = [regex]::Replace($encoded, '\*\*([^*]+)\*\*', '<strong>$1</strong>')
    $encoded = [regex]::Replace($encoded, '\*([^*]+)\*', '<em>$1</em>')
    return $encoded
}

function Convert-MarkdownBlockToHtml {
    param([AllowNull()][string] $Markdown)

    if ([string]::IsNullOrWhiteSpace($Markdown)) {
        return ""
    }

    $lines = $Markdown -split "`r?`n"
    $html = New-Object System.Collections.Generic.List[string]
    $paragraph = New-Object System.Collections.Generic.List[string]
    $inCode = $false
    $codeLanguage = ""
    $codeLines = New-Object System.Collections.Generic.List[string]
    $inList = $false
    $listType = ""
    $inQuote = $false
    $quoteLines = New-Object System.Collections.Generic.List[string]

    function Flush-Paragraph {
        if ($paragraph.Count -gt 0) {
            $html.Add("<p>$((($paragraph | ForEach-Object { Convert-InlineMarkdown $_ }) -join '<br>'))</p>")
            $paragraph.Clear()
        }
    }

    function Flush-List {
        if ($inList) {
            $html.Add("</$listType>")
            $script:inList = $false
            $script:listType = ""
        }
    }

    function Flush-Quote {
        if ($inQuote) {
            $html.Add("<blockquote>$((($quoteLines | ForEach-Object { Convert-InlineMarkdown $_ }) -join '<br>'))</blockquote>")
            $quoteLines.Clear()
            $script:inQuote = $false
        }
    }

    foreach ($line in $lines) {
        if ($line -match '^```(?<lang>.*)$') {
            if ($inCode) {
                $languageLabel = if ([string]::IsNullOrWhiteSpace($codeLanguage)) { "" } else { "<div class=`"code-lang`">$(Encode-Html $codeLanguage)</div>" }
                $html.Add("<div class=`"code-wrap`">$languageLabel<pre><code>$((Encode-Html ($codeLines -join "`n")))</code></pre></div>")
                $codeLines.Clear()
                $inCode = $false
                $codeLanguage = ""
            }
            else {
                Flush-Paragraph
                Flush-List
                Flush-Quote
                $inCode = $true
                $codeLanguage = $Matches.lang.Trim()
            }
            continue
        }

        if ($inCode) {
            $codeLines.Add($line)
            continue
        }

        if ([string]::IsNullOrWhiteSpace($line)) {
            Flush-Paragraph
            Flush-List
            Flush-Quote
            continue
        }

        if ($line -match '^(#{1,6})\s+(.+)$') {
            Flush-Paragraph
            Flush-List
            Flush-Quote
            $level = [Math]::Min($Matches[1].Length + 2, 6)
            $html.Add("<h$level>$(Convert-InlineMarkdown $Matches[2])</h$level>")
            continue
        }

        if ($line -match '^\s*[-*_]{3,}\s*$') {
            Flush-Paragraph
            Flush-List
            Flush-Quote
            $html.Add("<hr>")
            continue
        }

        if ($line -match '^\s*>\s?(.*)$') {
            Flush-Paragraph
            Flush-List
            $inQuote = $true
            $quoteLines.Add($Matches[1])
            continue
        }

        if ($line -match '^\s*[-*+]\s+(.+)$') {
            Flush-Paragraph
            Flush-Quote
            if (-not $inList -or $listType -ne "ul") {
                Flush-List
                $inList = $true
                $listType = "ul"
                $html.Add("<ul>")
            }
            $html.Add("<li>$(Convert-InlineMarkdown $Matches[1])</li>")
            continue
        }

        if ($line -match '^\s*\d+\.\s+(.+)$') {
            Flush-Paragraph
            Flush-Quote
            if (-not $inList -or $listType -ne "ol") {
                Flush-List
                $inList = $true
                $listType = "ol"
                $html.Add("<ol>")
            }
            $html.Add("<li>$(Convert-InlineMarkdown $Matches[1])</li>")
            continue
        }

        if ($line -match '^\|.*\|$') {
            Flush-Paragraph
            Flush-List
            Flush-Quote
            $cells = $line.Trim('|') -split '\|'
            $row = ($cells | ForEach-Object { "<td>$(Convert-InlineMarkdown $_.Trim())</td>" }) -join ''
            $html.Add("<table><tr>$row</tr></table>")
            continue
        }

        Flush-List
        Flush-Quote
        $paragraph.Add($line)
    }

    if ($inCode) {
        $html.Add("<div class=`"code-wrap`"><pre><code>$((Encode-Html ($codeLines -join "`n")))</code></pre></div>")
    }

    Flush-Paragraph
    Flush-List
    Flush-Quote

    return ($html -join "`n")
}

function Read-KiroMarkdownConversation {
    param([string] $Path)

    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $title = [IO.Path]::GetFileNameWithoutExtension($Path)
    if ($content -match '(?m)^#\s+(.+)$') {
        $title = $Matches[1].Trim()
    }

    $created = ""
    $modified = ""
    if ($content -match '(?m)^Created:\s*(.*)$') {
        $created = $Matches[1].Trim()
    }
    if ($content -match '(?m)^Last Modified:\s*(.*)$') {
        $modified = $Matches[1].Trim()
    }

    $blocks = New-Object System.Collections.Generic.List[object]
    $matches = [regex]::Matches($content, '(?ms)^##\s+(User|Assistant)\s*\r?\n(.*?)(?=^##\s+(?:User|Assistant)\s*$|\z)')
    foreach ($match in $matches) {
        $role = $match.Groups[1].Value
        $text = $match.Groups[2].Value.Trim("`r", "`n", " ")
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            $blocks.Add([pscustomobject]@{
                Role = $role
                Text = $text
            })
        }
    }

    return [pscustomobject]@{
        Title = $title
        Created = $created
        Modified = $modified
        Blocks = $blocks
        Source = $Path
    }
}

function Get-SessionNumber {
    param([string] $Name)

    if ($Name -match '(\d+)') {
        return [int] $Matches[1]
    }

    return 999999
}

function Get-SharedCss {
    return @'
:root {
  color-scheme: light;
  --bg: #f5f7fb;
  --panel: #ffffff;
  --line: #d7dde8;
  --text: #172033;
  --muted: #637083;
  --user: #dcecff;
  --assistant: #ffffff;
  --accent: #2563eb;
  --accent-2: #0f766e;
  --shadow: 0 12px 30px rgba(21, 31, 52, 0.10);
  font-family: "Segoe UI", Arial, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}
.app {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
}
.sidebar {
  border-right: 1px solid var(--line);
  background: #eef3fa;
  padding: 18px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: auto;
}
.brand {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 4px;
}
.meta {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}
.session-list {
  display: grid;
  gap: 8px;
  margin-top: 18px;
}
.session-link {
  display: block;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--text);
  text-decoration: none;
  background: rgba(255,255,255,0.56);
}
.session-link:hover,
.session-link.active {
  border-color: #b8c7dd;
  background: #fff;
}
.main {
  min-width: 0;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 5;
  background: rgba(245,247,251,0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
  padding: 18px 28px;
}
.title {
  font-size: 22px;
  line-height: 1.25;
  margin: 0 0 6px;
}
.chat {
  max-width: 1060px;
  margin: 0 auto;
  padding: 26px;
}
.message {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 18px;
  align-items: start;
}
.message.user {
  grid-template-columns: minmax(0, 1fr) 40px;
}
.message.user .avatar { grid-column: 2; }
.message.user .bubble { grid-column: 1; grid-row: 1; background: var(--user); border-color: #bfdbfe; }
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: var(--accent-2);
}
.message.user .avatar { background: var(--accent); }
.bubble {
  background: var(--assistant);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 16px 18px;
  overflow: hidden;
}
.role {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  margin-bottom: 10px;
}
.content {
  font-size: 15px;
  line-height: 1.62;
  overflow-wrap: anywhere;
}
.content p { margin: 0 0 12px; }
.content h3, .content h4, .content h5, .content h6 { margin: 18px 0 8px; line-height: 1.25; }
.content ul, .content ol { margin: 8px 0 14px 24px; padding: 0; }
.content li { margin: 4px 0; }
.content blockquote {
  margin: 12px 0;
  padding: 10px 14px;
  border-left: 4px solid #9fb3cf;
  background: rgba(255,255,255,.62);
}
.content code {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 0.92em;
  background: rgba(15,23,42,.08);
  border-radius: 5px;
  padding: 2px 5px;
}
.code-wrap {
  margin: 12px 0;
  border: 1px solid #c8d2e0;
  border-radius: 8px;
  overflow: hidden;
  background: #111827;
}
.code-lang {
  color: #cbd5e1;
  font-size: 12px;
  padding: 7px 10px;
  border-bottom: 1px solid rgba(255,255,255,.12);
}
pre {
  margin: 0;
  padding: 14px;
  overflow: auto;
}
pre code {
  background: transparent !important;
  color: #f8fafc;
  padding: 0 !important;
  white-space: pre;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  background: #fff;
}
td, th {
  border: 1px solid var(--line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
.attached-image {
  display: block;
  max-width: min(100%, 760px);
  max-height: 560px;
  object-fit: contain;
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 10px 0;
}
.index-grid {
  max-width: 980px;
  margin: 0 auto;
  padding: 28px;
  display: grid;
  gap: 10px;
}
.index-card {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  text-decoration: none;
  color: var(--text);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px 16px;
  box-shadow: var(--shadow);
}
.index-card:hover { border-color: #9fb3cf; }
.count-pill {
  flex: 0 0 auto;
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 820px) {
  .app { display: block; }
  .sidebar { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .session-list { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .topbar { padding: 16px; }
  .chat { padding: 16px; }
  .message, .message.user { grid-template-columns: 32px minmax(0, 1fr); }
  .message.user .avatar { grid-column: 1; }
  .message.user .bubble { grid-column: 2; }
  .avatar { width: 32px; height: 32px; }
}
'@
}

function Write-ChatHtml {
    param(
        $Conversation,
        [array] $AllSessions,
        [string] $OutputPath,
        [string] $CurrentFile
    )

    $css = Get-SharedCss
    $links = New-Object System.Collections.Generic.List[string]
    foreach ($session in $AllSessions) {
        $active = if ($session.FileName -eq $CurrentFile) { " active" } else { "" }
        $links.Add("<a class=`"session-link$active`" href=`"$($session.FileName)`">$(Encode-Html $session.Title)</a>")
    }

    $messages = New-Object System.Collections.Generic.List[string]
    foreach ($block in $Conversation.Blocks) {
        $roleClass = $block.Role.ToLowerInvariant()
        $initial = if ($block.Role -eq "User") { "YOU" } else { "AI" }
        $messages.Add(@"
<section class="message $roleClass">
  <div class="avatar">$initial</div>
  <article class="bubble">
    <div class="role">$($block.Role)</div>
    <div class="content">$(Convert-MarkdownBlockToHtml $block.Text)</div>
  </article>
</section>
"@)
    }

    $html = @"
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>$(Encode-Html $Conversation.Title)</title>
  <style>
$css
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">DRISHTI Kiro Sessions</div>
      <div class="meta">$($AllSessions.Count) exported chats<br>Generated from visible user and assistant messages</div>
      <nav class="session-list">
$($links -join "`n")
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <h1 class="title">$(Encode-Html $Conversation.Title)</h1>
        <div class="meta">Created: $(Encode-Html $Conversation.Created) &nbsp; Last Modified: $(Encode-Html $Conversation.Modified)</div>
      </header>
      <div class="chat">
$($messages -join "`n")
      </div>
    </main>
  </div>
</body>
</html>
"@

    Set-Content -LiteralPath $OutputPath -Value $html -Encoding UTF8
}

function Write-IndexHtml {
    param([array] $Sessions, [string] $OutputPath)

    $css = Get-SharedCss
    $cards = New-Object System.Collections.Generic.List[string]
    foreach ($session in $Sessions) {
        $cards.Add("<a class=`"index-card`" href=`"$($session.FileName)`"><span>$(Encode-Html $session.Title)</span><span class=`"count-pill`">$($session.Count) messages</span></a>")
    }

    $html = @"
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DRISHTI Kiro Sessions</title>
  <style>
$css
  </style>
</head>
<body>
  <main class="main">
    <header class="topbar">
      <h1 class="title">DRISHTI Kiro Sessions</h1>
      <div class="meta">$($Sessions.Count) exported chat transcripts rendered as chat-style HTML</div>
    </header>
    <section class="index-grid">
$($cards -join "`n")
    </section>
  </main>
</body>
</html>
"@

    Set-Content -LiteralPath $OutputPath -Value $html -Encoding UTF8
}

function Main {
    if (-not (Test-Path -LiteralPath $SourceRoot)) {
        throw "Source folder not found: $SourceRoot"
    }

    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    $sourceImages = Join-Path $SourceRoot "images"
    $outputImages = Join-Path $OutputRoot "images"
    if (Test-Path -LiteralPath $sourceImages) {
        New-Item -ItemType Directory -Force -Path $outputImages | Out-Null
        Get-ChildItem -LiteralPath $sourceImages -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination $outputImages -Force
            }
    }

    $markdownFiles = Get-ChildItem -LiteralPath $SourceRoot -Filter "*.md" -File |
        Sort-Object @{ Expression = { Get-SessionNumber $_.BaseName } }, Name

    $conversations = New-Object System.Collections.Generic.List[object]
    foreach ($file in $markdownFiles) {
        $conversation = Read-KiroMarkdownConversation -Path $file.FullName
        $fileName = [IO.Path]::ChangeExtension($file.Name, ".html")
        $conversations.Add([pscustomobject]@{
            Title = $conversation.Title
            Created = $conversation.Created
            Modified = $conversation.Modified
            Blocks = $conversation.Blocks
            FileName = $fileName
            Count = $conversation.Blocks.Count
        })
    }

    $sessionArray = @()
    foreach ($conversation in $conversations) {
        $sessionArray += $conversation
    }

    foreach ($conversation in $sessionArray) {
        $path = Join-Path $OutputRoot $conversation.FileName
        Write-ChatHtml -Conversation $conversation -AllSessions $sessionArray -OutputPath $path -CurrentFile $conversation.FileName
    }

    Write-IndexHtml -Sessions $sessionArray -OutputPath (Join-Path $OutputRoot "index.html")

    Write-Host "HTML sessions generated: $($conversations.Count)"
    Write-Host "Output:"
    Write-Host $OutputRoot
}

Main
