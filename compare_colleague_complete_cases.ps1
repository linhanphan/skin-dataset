param(
    [string]$WorkbookPath = "complete_case_chemical_lists_ICE105_Skin209.xlsx",
    [string]$OutputDir = "comparison_outputs"
)

$ErrorActionPreference = "Stop"

function Get-CellColumnIndex {
    param([string]$CellRef)

    $letters = ([regex]::Match($CellRef, "^[A-Z]+")).Value
    $index = 0
    foreach ($char in $letters.ToCharArray()) {
        $index = ($index * 26) + ([int][char]$char - [int][char]'A' + 1)
    }
    return $index
}

function Get-OpenXmlText {
    param($Node)

    if ($null -eq $Node) {
        return ""
    }

    $texts = $Node.GetElementsByTagName("t")
    if ($texts.Count -eq 0) {
        return $Node.InnerText
    }

    return (($texts | ForEach-Object { $_.InnerText }) -join "")
}

function Read-XlsxSheet {
    param(
        [string]$WorkbookPath,
        [string]$SheetName
    )

    $fullWorkbookPath = (Resolve-Path $WorkbookPath).Path
    $extractDir = Join-Path (Resolve-Path ".").Path (".xlsx_tmp_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $extractDir | Out-Null

    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($fullWorkbookPath, $extractDir)

        [xml]$workbook = Get-Content (Join-Path $extractDir "xl\workbook.xml")
        [xml]$rels = Get-Content (Join-Path $extractDir "xl\_rels\workbook.xml.rels")

        $ns = New-Object System.Xml.XmlNamespaceManager($workbook.NameTable)
        $ns.AddNamespace("m", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
        $ns.AddNamespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")

        $sheetNode = $workbook.SelectSingleNode("//m:sheet[@name='$SheetName']", $ns)
        if ($null -eq $sheetNode) {
            throw "Sheet not found: $SheetName"
        }

        $relId = $sheetNode.GetAttribute("id", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
        $relNode = $rels.Relationships.Relationship | Where-Object { $_.Id -eq $relId } | Select-Object -First 1
        if ($null -eq $relNode) {
            throw "Worksheet relationship not found for sheet: $SheetName"
        }

        $sheetPath = Join-Path (Join-Path $extractDir "xl") $relNode.Target

        $sharedStrings = @()
        $sharedPath = Join-Path $extractDir "xl\sharedStrings.xml"
        if (Test-Path $sharedPath) {
            [xml]$sharedXml = Get-Content $sharedPath
            $sharedStrings = @($sharedXml.sst.si | ForEach-Object { Get-OpenXmlText $_ })
        }

        [xml]$sheetXml = Get-Content $sheetPath
        $sheetNs = New-Object System.Xml.XmlNamespaceManager($sheetXml.NameTable)
        $sheetNs.AddNamespace("m", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")

        $rows = @()
        foreach ($row in $sheetXml.SelectNodes("//m:sheetData/m:row", $sheetNs)) {
            $values = @{}
            foreach ($cell in $row.SelectNodes("m:c", $sheetNs)) {
                $colIndex = Get-CellColumnIndex $cell.r
                $valueNode = $cell.SelectSingleNode("m:v", $sheetNs)
                $raw = if ($valueNode) { $valueNode.InnerText } else { "" }

                if ($cell.t -eq "s" -and $raw -ne "") {
                    $value = $sharedStrings[[int]$raw]
                } elseif ($cell.t -eq "inlineStr") {
                    $value = Get-OpenXmlText $cell
                } else {
                    $value = $raw
                }

                $values[$colIndex] = $value
            }
            if ($values.Count -gt 0) {
                $rows += ,$values
            }
        }

        if ($rows.Count -lt 2) {
            return @()
        }

        $headers = @()
        $maxCol = ($rows[0].Keys | ForEach-Object { [int]$_ } | Measure-Object -Maximum).Maximum
        for ($i = 1; $i -le $maxCol; $i++) {
            $header = [string]$rows[0][$i]
            if ([string]::IsNullOrWhiteSpace($header)) {
                $header = "Column$i"
            }
            $headers += $header
        }

        $objects = @()
        foreach ($row in $rows[1..($rows.Count - 1)]) {
            $obj = [ordered]@{}
            for ($i = 1; $i -le $headers.Count; $i++) {
                $obj[$headers[$i - 1]] = [string]$row[$i]
            }
            $objects += [pscustomobject]$obj
        }

        return $objects
    } finally {
        if (Test-Path $extractDir) {
            Remove-Item -LiteralPath $extractDir -Recurse -Force
        }
    }
}

function Get-NormalizedKey {
    param($Row)

    $cas = ""
    if ($Row.PSObject.Properties.Name -contains "CAS") {
        $cas = [string]$Row.CAS
    }

    $cas = $cas.Trim()
    if ($cas -match "^\d{4}-(\d{1,2})-(\d{1,2})(?: 00:00:00)?$") {
        $parts = $cas -split "[- ]"
        $year = [int]$parts[0]
        $month = [int]$parts[1]
        $day = [int]$parts[2]
        $prefix = if ($year -ge 1900 -and $year -le 1999) { $year - 1900 } else { $year }
        $cas = "{0}-{1:D2}-{2}" -f $prefix, $month, $day
    }

    if ($cas.ToLowerInvariant() -eq "nan") {
        $cas = ""
    }

    if (-not [string]::IsNullOrWhiteSpace($cas)) {
        return "CAS:" + $cas.Trim().ToUpperInvariant()
    }

    $chemical = ""
    if ($Row.PSObject.Properties.Name -contains "Chemical") {
        $chemical = [string]$Row.Chemical
    }

    return "CHEM:" + $chemical.Trim().ToUpperInvariant()
}

function Add-ComparisonFields {
    param(
        [object[]]$Rows,
        [hashtable]$OtherSet,
        [string]$Status
    )

    $Rows | ForEach-Object {
        $_ | Add-Member -NotePropertyName comparison_status -NotePropertyValue $Status -Force
        $_ | Add-Member -NotePropertyName comparison_key -NotePropertyValue (Get-NormalizedKey $_) -Force
        $_
    }
}

function Compare-Dataset {
    param(
        [string]$Name,
        [object[]]$ColleagueRows,
        [object[]]$OurCompleteRows,
        [object[]]$OurFullRows,
        [string]$OutputDir
    )

    $colleagueByKey = @{}
    foreach ($row in $ColleagueRows) {
        $colleagueByKey[(Get-NormalizedKey $row)] = $row
    }

    $ourCompleteByKey = @{}
    foreach ($row in $OurCompleteRows) {
        $ourCompleteByKey[(Get-NormalizedKey $row)] = $row
    }

    $ourFullByKey = @{}
    foreach ($row in $OurFullRows) {
        $ourFullByKey[(Get-NormalizedKey $row)] = $row
    }

    $colleagueOnly = @()
    foreach ($key in $colleagueByKey.Keys) {
        if (-not $ourCompleteByKey.ContainsKey($key)) {
            $base = $colleagueByKey[$key]
            if ($ourFullByKey.ContainsKey($key)) {
                $full = $ourFullByKey[$key]
                $base | Add-Member -NotePropertyName our_full_complete_case -NotePropertyValue $full.complete_case -Force
                foreach ($col in @("KE1_call", "KE2_call", "KE3_call", "LLNA_call", "KE1_metric", "KE2_metric", "KE3_metric", "LLNA_EC3", "KS_call", "LuSens_call", "hCLAT_call", "USENS_call")) {
                    if ($full.PSObject.Properties.Name -contains $col) {
                        $base | Add-Member -NotePropertyName ("our_full_" + $col) -NotePropertyValue $full.$col -Force
                    }
                }
            } else {
                $base | Add-Member -NotePropertyName our_full_complete_case -NotePropertyValue "not_found_in_our_full_output" -Force
            }
            $colleagueOnly += $base
        }
    }

    $oursOnly = @()
    foreach ($key in $ourCompleteByKey.Keys) {
        if (-not $colleagueByKey.ContainsKey($key)) {
            $oursOnly += $ourCompleteByKey[$key]
        }
    }

    $common = @()
    foreach ($key in $colleagueByKey.Keys) {
        if ($ourCompleteByKey.ContainsKey($key)) {
            $common += $colleagueByKey[$key]
        }
    }

    $colleagueOnly | Export-Csv (Join-Path $OutputDir "${Name}_colleague_only.csv") -NoTypeInformation
    $oursOnly | Export-Csv (Join-Path $OutputDir "${Name}_ours_only.csv") -NoTypeInformation
    $common | Export-Csv (Join-Path $OutputDir "${Name}_common.csv") -NoTypeInformation

    [pscustomobject]@{
        dataset = $Name
        colleague_count = $ColleagueRows.Count
        ours_count = $OurCompleteRows.Count
        common_count = $common.Count
        colleague_only_count = $colleagueOnly.Count
        ours_only_count = $oursOnly.Count
    }
}

function Has-Value {
    param(
        $Row,
        [string]$Column
    )

    return ($Row.PSObject.Properties.Name -contains $Column) -and -not [string]::IsNullOrWhiteSpace([string]$Row.$Column)
}

function Add-IceReverseFields {
    param($Row)

    $ke1 = ([string]$Row.KE1_call) -replace "\.0$", ""
    $ke2 = ([string]$Row.KE2_call) -replace "\.0$", ""
    $ke3 = ([string]$Row.KE3_call) -replace "\.0$", ""

    if (Has-Value $Row "LLNA_EC3") {
        $llna = if ([double]$Row.LLNA_EC3 -gt 0) { "1" } else { "0" }
        $llnaSource = "LLNA_EC3"
    } else {
        $llna = ([string]$Row.LLNA_call) -replace "\.0$", ""
        $llnaSource = "LLNA_call"
    }

    $misclassified = if (($ke1 -ne $llna) -or ($ke2 -ne $llna) -or ($ke3 -ne $llna)) { "1" } else { "0" }

    $Row | Add-Member -NotePropertyName reverse_pattern -NotePropertyValue "$ke1$ke2$ke3" -Force
    $Row | Add-Member -NotePropertyName reverse_LLNA_call -NotePropertyValue $llna -Force
    $Row | Add-Member -NotePropertyName reverse_LLNA_source -NotePropertyValue $llnaSource -Force
    $Row | Add-Member -NotePropertyName reverse_misclassified -NotePropertyValue $misclassified -Force
    return $Row
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$iceColleague = @(Read-XlsxSheet -WorkbookPath $WorkbookPath -SheetName "ICE_105")
$skinColleague = @(Read-XlsxSheet -WorkbookPath $WorkbookPath -SheetName "SkinSensDB_209")

$iceColleague | Export-Csv (Join-Path $OutputDir "colleague_ICE_105.csv") -NoTypeInformation
$skinColleague | Export-Csv (Join-Path $OutputDir "colleague_SkinSensDB_209.csv") -NoTypeInformation

$iceOurComplete = @(Import-Csv "ICE_complete_cases_from_raw.csv")
$skinOurComplete = @(Import-Csv "Skin_complete_cases_from_raw.csv")
$iceOurFull = @(Import-Csv "ICE_endpoint_presence_from_raw.csv")
$skinOurFull = @(Import-Csv "Skin_endpoint_presence_from_raw.csv")

$summary = @(
    Compare-Dataset -Name "ICE" -ColleagueRows $iceColleague -OurCompleteRows $iceOurComplete -OurFullRows $iceOurFull -OutputDir $OutputDir
    Compare-Dataset -Name "SkinSensDB" -ColleagueRows $skinColleague -OurCompleteRows $skinOurComplete -OurFullRows $skinOurFull -OutputDir $OutputDir
)

$summary | Export-Csv (Join-Path $OutputDir "comparison_summary.csv") -NoTypeInformation

$iceColleagueKeys = @{}
foreach ($row in $iceColleague) {
    $iceColleagueKeys[(Get-NormalizedKey $row)] = $true
}

$iceReverseCandidate = @(
    $iceOurFull |
        Where-Object {
            (Has-Value $_ "KE1_call") -and
            (Has-Value $_ "KE2_call") -and
            (Has-Value $_ "KE3_call") -and
            ((Has-Value $_ "LLNA_call") -or (Has-Value $_ "LLNA_EC3"))
        } |
        ForEach-Object {
            Add-IceReverseFields $_
        }
)

$iceReverseCandidate | Export-Csv (Join-Path $OutputDir "ICE_reverse_candidate_llna_call_or_ec3.csv") -NoTypeInformation
$iceReverseCandidate |
    Where-Object { -not $iceColleagueKeys.ContainsKey((Get-NormalizedKey $_)) } |
    Export-Csv (Join-Path $OutputDir "ICE_reverse_candidate_not_in_colleague.csv") -NoTypeInformation

$summary | Format-Table -AutoSize

Write-Host ""
Write-Host "ICE reverse candidate rule: KE1_call + KE2_call + KE3_call + (LLNA_call OR LLNA_EC3)"
Write-Host ("ICE reverse candidate rows: " + $iceReverseCandidate.Count)
Write-Host ("ICE reverse candidate not in colleague sheet: " + (@($iceReverseCandidate | Where-Object { -not $iceColleagueKeys.ContainsKey((Get-NormalizedKey $_)) }).Count))
