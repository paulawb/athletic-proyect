$ErrorActionPreference = "Stop"

function Read-PostgresConnection([string]$prompt) {
    $secureUri = Read-Host $prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUri)

    try {
        $rawUri = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        $uri = [Uri]::new($rawUri)
        if ($uri.Scheme -notin @("postgres", "postgresql")) {
            throw "La conexión debe ser una URL postgres:// o postgresql://."
        }

        $credentials = [Uri]::UnescapeDataString($uri.UserInfo).Split(":", 2)
        if ($credentials.Count -ne 2 -or [string]::IsNullOrWhiteSpace($credentials[0])) {
            throw "La URL de conexión debe incluir usuario y contraseña."
        }

        $database = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart("/"))
        if ([string]::IsNullOrWhiteSpace($database)) {
            throw "La URL de conexión debe especificar una base de datos."
        }

        return [PSCustomObject]@{
            Host     = $uri.Host
            Port     = if ($uri.IsDefaultPort) { 5432 } else { $uri.Port }
            Database = $database
            User     = $credentials[0]
            Password = $credentials[1]
        }
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secureUri.Dispose()
    }
}

function Escape-PassfileField([string]$value) {
    return $value.Replace("\", "\\").Replace(":", "\:")
}

function Invoke-Psql([string]$executable, $connection, [string]$sql) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            $result = @(& $executable `
                --no-password `
                --no-psqlrc `
                --quiet `
                --tuples-only `
                --no-align `
                --field-separator "`t" `
                --host $connection.Host `
                --port $connection.Port `
                --username $connection.User `
                --dbname $connection.Database `
                --command $sql 2>&1)
            $exitCode = $LASTEXITCODE
            if ($exitCode -eq 0) {
                return @($result | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
            }

            $diagnostic = ($result | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join " "
            $diagnostic = $diagnostic -replace "(?i)postgres(?:ql)?://\S+", "[connection hidden]"
            $diagnostic = $diagnostic -replace "(?i)(password\s*[=:]\s*)\S+", '$1[hidden]'
            if ($diagnostic.Length -gt 500) {
                $diagnostic = $diagnostic.Substring(0, 500)
            }

            $isTransientDnsFailure = $diagnostic -match "(?i)could not translate host name|name or service not known|temporary failure in name resolution"
            if (-not $isTransientDnsFailure -or $attempt -eq 3) {
                throw "PostgreSQL connection/query failed: $diagnostic"
            }
            Start-Sleep -Seconds 2
        }
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Get-PublicTableCounts([string]$executable, $connection) {
    $listTablesSql = @"
SELECT tablename
FROM pg_catalog.pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
"@
    $tableNames = @(Invoke-Psql $executable $connection $listTablesSql)
    $counts = @{}
    foreach ($tableName in $tableNames) {
        $quotedIdentifier = $tableName.Replace('"', '""')
        $quotedLabel = $tableName.Replace("'", "''")
        $sql = "SELECT json_build_array('$quotedLabel', count(*)::bigint)::text FROM public.`"$quotedIdentifier`";"
        $row = @(Invoke-Psql $executable $connection $sql)
        if ($row.Count -ne 1) {
            throw "No se pudo contar de forma segura la tabla '$tableName'."
        }
        try {
            $parts = ConvertFrom-Json -InputObject $row[0] -ErrorAction Stop
        }
        catch {
            throw "No se pudo interpretar el conteo de filas de la tabla '$tableName'."
        }
        if ($parts.Count -ne 2 -or $parts[0] -cne $tableName) {
            throw "No se pudo interpretar el conteo de filas de la tabla '$tableName'."
        }
        $counts[[string]$parts[0]] = [long]$parts[1]
    }
    return $counts
}

$pgBin = $null
$postgresRoot = Join-Path $env:ProgramFiles "PostgreSQL"
if (Test-Path $postgresRoot) {
    $pgBin = Get-ChildItem $postgresRoot -Directory |
        Sort-Object { [int]$_.Name } -Descending |
        ForEach-Object { Join-Path $_.FullName "bin" } |
        Where-Object {
            (Test-Path (Join-Path $_ "pg_dump.exe")) -and
            (Test-Path (Join-Path $_ "pg_restore.exe")) -and
            (Test-Path (Join-Path $_ "psql.exe"))
        } |
        Select-Object -First 1
}

if (-not $pgBin) {
    throw "No encuentro pg_dump, pg_restore y psql. Instala las herramientas de PostgreSQL y vuelve a ejecutar."
}

$pgDump = Join-Path $pgBin "pg_dump.exe"
$pgRestore = Join-Path $pgBin "pg_restore.exe"
$psql = Join-Path $pgBin "psql.exe"
$source = $null
$destination = $null
$passFile = Join-Path $env:TEMP ("athletic-pgpass-" + [guid]::NewGuid().ToString("N"))
$backup = Join-Path $env:USERPROFILE ("athletic-analysis-render-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".dump")

try {
    Write-Host "Este proceso solo lee la base Render y copia su contenido a Neon."
    Write-Host "El archivo de respaldo se conservará en tu perfil de Windows."
    $source = Read-PostgresConnection "Pega la URL EXTERNA de Render (entrada oculta)"
    $destination = Read-PostgresConnection "Pega la URL DIRECTA de Neon (entrada oculta; no uses pooled)"

    if ($destination.Host -match "-pooler\.") {
        $destination.Host = $destination.Host -replace "-pooler(?=\.)", ""
        Write-Host "Se detectó la URL pooled de Neon; para pg_restore usaré el hostname Direct sin '-pooler'."
    }

    $confirmation = Read-Host "Escribe COPIAR para crear el respaldo y copiarlo a Neon"
    if ($confirmation -cne "COPIAR") {
        throw "Cancelado; no se modificó ninguna base de datos."
    }

    $passLines = @(
        "$((Escape-PassfileField $source.Host)):$($source.Port):$((Escape-PassfileField $source.Database)):$((Escape-PassfileField $source.User)):$((Escape-PassfileField $source.Password))"
        "$((Escape-PassfileField $destination.Host)):$($destination.Port):$((Escape-PassfileField $destination.Database)):$((Escape-PassfileField $destination.User)):$((Escape-PassfileField $destination.Password))"
    )
    [IO.File]::WriteAllText($passFile, ($passLines -join "`n"), [Text.UTF8Encoding]::new($false))

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl $passFile
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleAll($rule)
    }
    $fileRule = [Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    )
    [void]$acl.AddAccessRule($fileRule)
    Set-Acl -Path $passFile -AclObject $acl

    $env:PGPASSFILE = $passFile
    $env:PGSSLMODE = "require"
    $env:PGCONNECT_TIMEOUT = "20"

    Write-Host "Checking the Render source connection..."
    [void](Invoke-Psql $psql $source "SELECT current_database();")
    Write-Host "Render database connection is OK."
    Write-Host "Checking the Neon destination connection..."
    [void](Invoke-Psql $psql $destination "SELECT current_database();")
    Write-Host "Neon database connection is OK."

    Write-Host "Creando respaldo de Render..."
    $dumpOutput = @(& $pgDump `
        --format=custom `
        --no-owner `
        --no-acl `
        --no-password `
        --host $source.Host `
        --port $source.Port `
        --username $source.User `
        --dbname $source.Database `
        --file $backup 2>&1)
    $dumpExitCode = $LASTEXITCODE
    if ($dumpExitCode -ne 0) {
        $diagnostic = ($dumpOutput | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join " "
        $diagnostic = $diagnostic -replace "(?i)postgres(?:ql)?://\S+", "[connection hidden]"
        $diagnostic = $diagnostic -replace "(?i)(password\s*[=:]\s*)\S+", '$1[hidden]'
        if ($diagnostic.Length -gt 500) {
            $diagnostic = $diagnostic.Substring(0, 500)
        }
        Write-Host "Render backup failed: $diagnostic"
        throw "The Render backup failed. Neon was not modified."
    }
    if (-not (Test-Path $backup) -or (Get-Item $backup).Length -eq 0) {
        throw "El respaldo no se creó correctamente; Neon no se modificó."
    }

    & $pgRestore --list $backup *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "El archivo de respaldo no pasó la validación; Neon no se modificó."
    }

    $sourceCounts = Get-PublicTableCounts $psql $source
    try {
        $destinationCounts = Get-PublicTableCounts $psql $destination
    }
    catch {
        throw "No se pudo revisar Neon antes de importar. No se modificó ninguna base. Conserva el respaldo y vuelve a ejecutar el asistente."
    }
    if ($destinationCounts.Count -gt 0) {
        $countDifferences = @()
        foreach ($table in $sourceCounts.Keys) {
            if (-not $destinationCounts.ContainsKey($table)) {
                $countDifferences += "${table}: falta en Neon"
            }
            elseif ($sourceCounts[$table] -ne $destinationCounts[$table]) {
                $countDifferences += "${table}: Render=$($sourceCounts[$table]), Neon=$($destinationCounts[$table])"
            }
        }
        foreach ($table in $destinationCounts.Keys) {
            if (-not $sourceCounts.ContainsKey($table)) {
                $countDifferences += "${table}: solo existe en Neon ($($destinationCounts[$table]) filas)"
            }
        }

        if ($countDifferences.Count -eq 0) {
            Write-Host "Render y Neon tienen las mismas tablas públicas y el mismo número de filas."
            Write-Host "No se importó nada ni se modificó ninguna base. Revisa ahora la aplicación para confirmar los registros."
            Write-Host "Respaldo local de Render conservado en: $backup"
            return
        }

        Write-Host "Render y Neon tienen distinto contenido (solo se muestran nombres de tabla y cantidades):"
        $countDifferences | ForEach-Object { Write-Host "  $_" }
        throw "No se importó ni modificó nada. No borres las tablas de Neon; compara los datos de la aplicación antes de decidir el siguiente paso."
    }

    Write-Host "Importando los datos a Neon..."
    & $pgRestore `
        --no-owner `
        --no-acl `
        --exit-on-error `
        --single-transaction `
        --no-password `
        --host $destination.Host `
        --port $destination.Port `
        --username $destination.User `
        --dbname $destination.Database `
        $backup
    if ($LASTEXITCODE -ne 0) {
        throw "La restauración falló. El respaldo se conserva en $backup; no cambies DATABASE_URL todavía."
    }

    try {
        $destinationCounts = Get-PublicTableCounts $psql $destination
    }
    catch {
        throw "Neon aceptó la restauración, pero falló la verificación final. No borres las tablas de Neon. Conserva el respaldo $backup y vuelve a ejecutar este asistente: comparará las tablas existentes y no volverá a importarlas."
    }
    $differences = @()
    foreach ($table in $sourceCounts.Keys) {
        if (-not $destinationCounts.ContainsKey($table) -or $sourceCounts[$table] -ne $destinationCounts[$table]) {
            $differences += $table
        }
    }
    foreach ($table in $destinationCounts.Keys) {
        if (-not $sourceCounts.ContainsKey($table)) {
            $differences += $table
        }
    }

    if ($differences.Count -gt 0) {
        throw "La verificación encontró diferencias en tablas: $($differences -join ', '). Conserva el respaldo y no cambies DATABASE_URL."
    }

    $version = @(Invoke-Psql $psql $destination `
        "SELECT version_num FROM public.alembic_version ORDER BY version_num DESC LIMIT 1;")

    Write-Host ""
    Write-Host "Copia y verificación terminadas."
    Write-Host "Tablas comparadas: $($sourceCounts.Count)"
    Write-Host "Revisión Alembic en Neon: $($version -join ', ')"
    Write-Host "Respaldo local conservado en: $backup"
    Write-Host "La base Render no se modificó. No la elimines hasta verificar la aplicación."
}
finally {
    Remove-Item Env:PGPASSFILE -ErrorAction SilentlyContinue
    Remove-Item Env:PGSSLMODE -ErrorAction SilentlyContinue
    Remove-Item Env:PGCONNECT_TIMEOUT -ErrorAction SilentlyContinue
    Remove-Item $passFile -Force -ErrorAction SilentlyContinue
    if ($source) {
        $source.Password = $null
    }
    if ($destination) {
        $destination.Password = $null
    }
}
