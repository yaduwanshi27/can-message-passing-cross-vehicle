# STAGE 1C - read-only pre-freeze checks. Writes only into $Out.
param(
  [string]$Root = "C:\dataset\can-train-and-test",
  [string]$Out  = "C:\dataset\can-train-and-test\_stage1c_outputs"
)
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$log = Join-Path $Out "stage1c_log.txt"
function L($s) { $s | Out-File -FilePath $log -Append -Encoding utf8 }
"STAGE 1C started " + (Get-Date -Format s) | Out-File -FilePath $log -Encoding utf8

# ---------- A. System profile ----------
$sys = [ordered]@{}
try {
  $cpu = Get-CimInstance Win32_Processor
  $sys.cpu = @($cpu | ForEach-Object { [ordered]@{ name=$_.Name; cores=$_.NumberOfCores; threads=$_.NumberOfLogicalProcessors; maxMHz=$_.MaxClockSpeed } })
  $cs = Get-CimInstance Win32_ComputerSystem
  $sys.manufacturer = $cs.Manufacturer; $sys.model = $cs.Model
  $sys.ram_total_GB = [math]::Round($cs.TotalPhysicalMemory/1GB,2)
  $os = Get-CimInstance Win32_OperatingSystem
  $sys.ram_free_GB = [math]::Round($os.FreePhysicalMemory*1KB/1GB,2)
  $sys.os = $os.Caption + " " + $os.Version + " " + $os.OSArchitecture
  $sys.ram_modules = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object { [ordered]@{ GB=[math]::Round($_.Capacity/1GB,1); speed=$_.Speed } })
  $sys.gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { [ordered]@{ name=$_.Name; adapterRAM_MB=[math]::Round($_.AdapterRAM/1MB); driver=$_.DriverVersion } })
  $sys.disks = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object { [ordered]@{ drive=$_.DeviceID; size_GB=[math]::Round($_.Size/1GB,1); free_GB=[math]::Round($_.FreeSpace/1GB,1); fs=$_.FileSystem } })
  try { $sys.physical_disks = @(Get-PhysicalDisk | ForEach-Object { [ordered]@{ name=$_.FriendlyName; media=[string]$_.MediaType; bus=[string]$_.BusType; size_GB=[math]::Round($_.Size/1GB,1) } }) } catch { $sys.physical_disks = "n/a" }
  $nv = Get-Command nvidia-smi -ErrorAction SilentlyContinue
  if ($nv) { $sys.nvidia_smi = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv 2>&1 | Out-String) } else { $sys.nvidia_smi = "not found" }
  $cands = @("$env:LOCALAPPDATA\Python","$env:LOCALAPPDATA\Programs\Python","$env:USERPROFILE\anaconda3","$env:USERPROFILE\miniconda3","C:\ProgramData\anaconda3","C:\ProgramData\miniconda3","C:\Python312","C:\Python311","C:\Python310","$env:LOCALAPPDATA\Microsoft\WindowsApps")
  $sys.python_dirs = @($cands | Where-Object { Test-Path $_ } | ForEach-Object { [ordered]@{ path=$_; exes=@(Get-ChildItem -Path $_ -Recurse -Filter python.exe -ErrorAction SilentlyContinue -Depth 3 | Select-Object -First 10 | ForEach-Object { $_.FullName }) } })
  $sys.where_python = (where.exe python 2>&1 | Out-String)
  $sys.where_conda = (where.exe conda 2>&1 | Out-String)
  $sys.where_git = (where.exe git 2>&1 | Out-String)
  $sys.wsl = (Get-Command wsl -ErrorAction SilentlyContinue) -ne $null
  $sys.dotnet_clr = [Environment]::Version.ToString()
  $sys.ps_version = $PSVersionTable.PSVersion.ToString()
} catch { $sys.error = $_.Exception.Message }
$sys | ConvertTo-Json -Depth 6 | Out-File -FilePath (Join-Path $Out "system_profile.json") -Encoding utf8
L "system profile written"

# ---------- B. Zip inspection (no extraction) ----------
try {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zinfo = @()
  Get-ChildItem -Path "C:\dataset" -File | ForEach-Object {
    $zinfo += "FILE " + $_.Name + " | " + $_.Length + " B | created " + $_.CreationTime.ToString("s") + " | modified " + $_.LastWriteTime.ToString("s")
  }
  $zips = Get-ChildItem -Path "C:\dataset" -File | Where-Object { $_.Extension -ieq ".zip" }
  foreach ($z in $zips) {
    $za = [System.IO.Compression.ZipFile]::OpenRead($z.FullName)
    try {
      $ents = $za.Entries
      $zinfo += "ZIP " + $z.Name + " entries=" + $ents.Count
      $tops = $ents | ForEach-Object { ($_.FullName -split '[\\/]')[0] } | Group-Object | ForEach-Object { $_.Name + " (" + $_.Count + ")" }
      $zinfo += "TOP-LEVEL: " + ($tops -join "; ")
      $csvRows = New-Object System.Collections.ArrayList
      foreach ($e in $ents) {
        [void]$csvRows.Add(('"' + $e.FullName + '",' + $e.Length + ',' + $e.CompressedLength + ',' + $e.LastWriteTime.ToString("s")))
        if (-not $e.FullName.ToLower().EndsWith(".csv") -and $e.Length -gt 0 -and $e.Length -lt 2MB) {
          $zinfo += "---- NON-CSV ENTRY: " + $e.FullName + " (" + $e.Length + " B, " + $e.LastWriteTime.ToString("s") + ")"
          $sr = New-Object System.IO.StreamReader($e.Open())
          $zinfo += $sr.ReadToEnd()
          $sr.Close()
          $zinfo += "---- END ENTRY"
        } elseif (-not $e.FullName.ToLower().EndsWith(".csv")) {
          $zinfo += "NON-CSV (not read): " + $e.FullName + " " + $e.Length + " B"
        }
      }
      ("full_name,uncompressed_bytes,compressed_bytes,last_write") | Out-File -FilePath (Join-Path $Out ("zip_entries_" + $z.BaseName + ".csv")) -Encoding utf8
      $csvRows | Out-File -FilePath (Join-Path $Out ("zip_entries_" + $z.BaseName + ".csv")) -Append -Encoding utf8
    } finally { $za.Dispose() }
  }
  $zinfo | Out-File -FilePath (Join-Path $Out "zip_inspection.txt") -Encoding utf8
  L "zip inspection written"
} catch { L ("zip inspection error: " + $_.Exception.ToString()) }

# ---------- C. One read-only pass over CSVs ----------
$code = @'
using System;
using System.IO;
using System.Text;
using System.Linq;
using System.Globalization;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Text.RegularExpressions;

public static class PreFreeze
{
    static readonly CultureInfo IC = CultureInfo.InvariantCulture;
    static readonly int[] WS = new int[] { 32, 64, 128 };

    public class Res {
        public string Rel; public string Err = "";
        public long Rows;
        public Dictionary<string, long[]> Ids = new Dictionary<string, long[]>();
        public long[] NWin = new long[3], NPos = new long[3], Trail = new long[3];
        public double[] DurSum = new double[3];
        public long[] PosAttackFrames = new long[3];
        public long Nodes64Sum, Nodes64Max, Edges64Sum, Edges64Max, NegInSpan64;
        public long Nodes64PosSum, Edges64PosSum;
        public double FirstAts = double.NaN, LastAts = double.NaN;
    }

    public static Res Pass(string root, string rel) {
        var r = new Res(); r.Rel = rel;
        try {
            string[] p = rel.Split('/');
            string path = Path.Combine(root, p[0], p[1], p[2]);
            // first pass needs attack span for NegInSpan: do a light pre-scan of labels+timestamps inline by buffering window stats
            var winStart = new double[3]; var winLast = new double[3]; var winCnt = new int[3]; var winAtt = new int[3];
            var nodes = new HashSet<string>(); var edges = new HashSet<string>(); string prevId = null;
            var negWinTimes = new List<double[]>(); // [start,end] of negative 64-windows
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20))
            using (var sr = new StreamReader(fs, new UTF8Encoding(false, false), false, 1 << 20)) {
                sr.ReadLine();
                string line;
                while ((line = sr.ReadLine()) != null) {
                    if (line.Length == 0) continue;
                    string[] f = line.Split(',');
                    if (f.Length != 4) continue;
                    double ts; if (!double.TryParse(f[0], NumberStyles.Float, IC, out ts)) continue;
                    string id = f[1]; bool att = f[3] == "1";
                    r.Rows++;
                    long[] c; if (!r.Ids.TryGetValue(id, out c)) { c = new long[2]; r.Ids[id] = c; }
                    c[att ? 1 : 0]++;
                    if (att) { if (double.IsNaN(r.FirstAts)) r.FirstAts = ts; r.LastAts = ts; }
                    for (int k = 0; k < 3; k++) {
                        if (winCnt[k] == 0) { winStart[k] = ts; winAtt[k] = 0; }
                        winCnt[k]++; winLast[k] = ts; if (att) winAtt[k]++;
                        if (k == 1) {
                            nodes.Add(id);
                            if (prevId != null) edges.Add(prevId + ">" + id);
                            prevId = id;
                        }
                        if (winCnt[k] == WS[k]) {
                            r.NWin[k]++; r.DurSum[k] += winLast[k] - winStart[k];
                            if (winAtt[k] > 0) { r.NPos[k]++; r.PosAttackFrames[k] += winAtt[k]; }
                            if (k == 1) {
                                r.Nodes64Sum += nodes.Count; if (nodes.Count > r.Nodes64Max) r.Nodes64Max = nodes.Count;
                                r.Edges64Sum += edges.Count; if (edges.Count > r.Edges64Max) r.Edges64Max = edges.Count;
                                if (winAtt[k] > 0) { r.Nodes64PosSum += nodes.Count; r.Edges64PosSum += edges.Count; }
                                else negWinTimes.Add(new double[] { winStart[k], winLast[k] });
                                nodes.Clear(); edges.Clear(); prevId = null;
                            }
                            winCnt[k] = 0;
                        }
                    }
                }
                for (int k = 0; k < 3; k++) r.Trail[k] = winCnt[k];
            }
            if (!double.IsNaN(r.FirstAts)) {
                foreach (var w in negWinTimes) if (w[1] >= r.FirstAts && w[0] <= r.LastAts) r.NegInSpan64++;
            }
        } catch (Exception e) { r.Err = e.GetType().Name + ": " + e.Message; }
        return r;
    }

    public static int Run(string root, string outDir, string logPath) {
        var rels = new List<string>();
        foreach (var sd in Directory.GetDirectories(root).OrderBy(x => x, StringComparer.Ordinal)) {
            string st = Path.GetFileName(sd);
            if (!Regex.IsMatch(st, @"^set_\d+$")) continue;
            foreach (var bd in Directory.GetDirectories(sd).OrderBy(x => x, StringComparer.Ordinal))
                foreach (var f in Directory.GetFiles(bd, "*.csv").OrderBy(x => x.ToLowerInvariant(), StringComparer.Ordinal))
                    rels.Add(st + "/" + Path.GetFileName(bd) + "/" + Path.GetFileName(f));
        }
        var lk = new object();
        Action<string> log = s => { lock (lk) { File.AppendAllText(logPath, s + Environment.NewLine); } };
        log("pass C: " + rels.Count + " files");
        var res = new Res[rels.Count]; int done = 0;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        Parallel.For(0, rels.Count, new ParallelOptions { MaxDegreeOfParallelism = 4 }, i => {
            res[i] = Pass(root, rels[i]);
            int n = System.Threading.Interlocked.Increment(ref done);
            log("[" + n + "/" + rels.Count + "] " + rels[i] + " " + res[i].Err);
        });
        using (var w = new StreamWriter(Path.Combine(outDir, "file_id_counts.csv"), false, new UTF8Encoding(false))) {
            w.NewLine = "\n";
            w.WriteLine("relative_path,arbitration_id,n_attack0,n_attack1");
            foreach (var r in res.OrderBy(x => x.Rel, StringComparer.Ordinal))
                foreach (var kv in r.Ids.OrderBy(x => x.Key, StringComparer.Ordinal))
                    w.WriteLine(r.Rel + "," + kv.Key + "," + kv.Value[0] + "," + kv.Value[1]);
        }
        using (var w = new StreamWriter(Path.Combine(outDir, "file_window_stats.csv"), false, new UTF8Encoding(false))) {
            w.NewLine = "\n";
            var h = new List<string> { "relative_path", "rows", "error" };
            foreach (int W in WS) { h.Add("w" + W + "_windows"); h.Add("w" + W + "_pos"); h.Add("w" + W + "_trailing_frames"); h.Add("w" + W + "_dur_sum_s"); h.Add("w" + W + "_attack_frames_in_pos"); }
            h.AddRange(new[] { "w64_nodes_sum", "w64_nodes_max", "w64_edges_sum", "w64_edges_max", "w64_nodes_pos_sum", "w64_edges_pos_sum", "w64_neg_windows_within_attack_span", "first_attack_ts", "last_attack_ts" });
            w.WriteLine(string.Join(",", h));
            foreach (var r in res.OrderBy(x => x.Rel, StringComparer.Ordinal)) {
                var v = new List<string> { r.Rel, r.Rows.ToString(IC), r.Err.Replace(",", ";") };
                for (int k = 0; k < 3; k++) { v.Add(r.NWin[k].ToString(IC)); v.Add(r.NPos[k].ToString(IC)); v.Add(r.Trail[k].ToString(IC)); v.Add(r.DurSum[k].ToString("R", IC)); v.Add(r.PosAttackFrames[k].ToString(IC)); }
                v.AddRange(new[] { r.Nodes64Sum.ToString(IC), r.Nodes64Max.ToString(IC), r.Edges64Sum.ToString(IC), r.Edges64Max.ToString(IC), r.Nodes64PosSum.ToString(IC), r.Edges64PosSum.ToString(IC), r.NegInSpan64.ToString(IC),
                    double.IsNaN(r.FirstAts) ? "" : r.FirstAts.ToString("R", IC), double.IsNaN(r.LastAts) ? "" : r.LastAts.ToString("R", IC) });
                w.WriteLine(string.Join(",", v));
            }
        }
        int errors = res.Count(x => x.Err != "");
        log("pass C DONE errors=" + errors + " elapsed_s=" + (sw.ElapsedMilliseconds / 1000.0).ToString("F1", IC));
        return errors;
    }
}
'@
try {
  Add-Type -TypeDefinition $code -Language CSharp -ReferencedAssemblies System.Core
  $e = [PreFreeze]::Run($Root, $Out, $log)
  L ("STAGE 1C FINISHED errors=" + $e + " " + (Get-Date -Format s))
} catch { L ("FATAL pass C: " + $_.Exception.ToString()) }
