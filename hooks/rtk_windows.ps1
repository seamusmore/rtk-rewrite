# Windows sandbox tokens can make SHGetKnownFolderPath fail even though
# USERPROFILE still identifies the real user. RTK 0.49 reads the override below
# before calling that API. Preserve explicit overrides and the original hook
# integrity checks; never create or edit Claude configuration.
param([Parameter(Mandatory = $true)][string]$RtkCommand)

# The hook only supplies a simple RTK command. Recheck at this boundary too.
if ($RtkCommand -notmatch '^rtk ' -or $RtkCommand -match '[\r\n;&|<>`$(){}]') {
    throw 'Expected a simple RTK command'
}
$rtkPreviousClaudeDir = $env:CLAUDE_CONFIG_DIR
try {
    if (-not $env:CLAUDE_CONFIG_DIR -and $env:USERPROFILE) {
        $env:CLAUDE_CONFIG_DIR = Join-Path $env:USERPROFILE '.claude'
    }
    # Parse the exact rewritten command once in the original PowerShell shell.
    # Passing its tokens as script arguments would consume native '--'.
    # Use Python for stream handling: the sandbox's ConstrainedLanguage mode
    # forbids .NET console methods. PowerShell still parses native arguments.
    $runner = (Join-Path $PSScriptRoot 'rtk_run.py').Replace("'", "''")
    $invocation = $RtkCommand -replace '^rtk ', "python '$runner' "
    Invoke-Expression $invocation
    $rtkResult = $LASTEXITCODE
} finally {
    $env:CLAUDE_CONFIG_DIR = $rtkPreviousClaudeDir
}
exit $rtkResult
