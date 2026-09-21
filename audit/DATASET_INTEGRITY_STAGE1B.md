# DATASET_INTEGRITY_STAGE1B — can-train-and-test

**Scope:** Complete, read-only, full-file integrity audit of all CSVs under `C:\dataset\can-train-and-test`. No sampling, no feature building, no training, no files modified. Results are reported without interpretation or design recommendations.

**Date:** 2026-09-17 · **Prepared by:** Claude (research/computation worker)

**Evidence label for everything in this report unless stated otherwise: RAW-DATA VERIFIED** (computed by streaming every byte/line of every CSV on the user's machine).

## 0. How the audit was run

- Executed locally on device `desktop-ugbtsbn` (Windows 10, PowerShell 5.1, .NET CLR 4.0) by `_stage1b_outputs\RUN_STAGE1B_AUDIT_PS.bat` → `audit_stage1b.ps1` (inline C#). The installed Python (`pythoncore-3.14`) failed to launch ("install path was not found"), so the equivalent PowerShell/C# port was used; `audit_stage1b.py` is kept for reference only.
- Each CSV opened read-only (`FileAccess.Read`, `FileShare.Read`); SHA-256 over all bytes; then every line streamed with a 1 MB buffer. Up to 4 files in parallel. Files were not copied.
- Per-file log: `_stage1b_outputs\run_console.log`. Per-file results: `DATASET_FILE_MANIFEST_STAGE1B.csv` (one row per CSV, 53 columns).
- Files audited: **236** · files with processing errors: **0**.

- **Cross-implementation check:** an independent Python implementation (`audit_stage1b.py`, identical definitions) was run earlier on 7 CSVs copied during Stage 1. All fields matched the PowerShell/C# results except 2 values that differ only in the last printed float digit (e.g. `1672531377.877731` vs `1672531377.8777311`; .NET “R” vs Python float formatting). No count differed.
- **File-set check:** 236 CSVs audited = 236 in the Stage 1 listing; all byte sizes identical to Stage 1. Total CSV bytes 7,471,443,340 (+ README.md 2,272 = 7,471,445,612, the Stage 1 total).
- **Section order below:** D (schema) → B (duplicates) → C (leakage) → E (class balance) → F (anomalies) → A (per-file manifest).

### 0.1 Field definitions (fixed before the run)

| Field | Definition |
|---|---|
| `row_count` | Non-empty data lines after the header line. |
| `blank_line_count` | Empty lines (not counted as rows). |
| `malformed_row_count` | Rows with ≠4 comma-separated fields, OR timestamp not parseable as a finite float, OR arbitration_id not 1–8 hex chars, OR non-empty data_field not hex or >16 hex chars, OR attack ∉ {"0","1"}. A row is counted once; component counts are given separately. |
| `empty_data_field_count` | Rows whose data_field is the empty string (not counted as malformed). |
| `attack_ratio` | attack1_count / row_count. |
| `timestamp_decrease_count` | Rows whose timestamp is strictly smaller than the previous row's timestamp (file order). |
| `data_field_hexlen_min/max` | Length of data_field in hex characters (bytes = chars/2), over all rows incl. empty (=0); `_min_nonempty` excludes empty. |
| `attack_episode_count (row level)` | Number of maximal runs of consecutive `attack=1` rows in file order. `attack_contiguity` = none / single_contiguous / multiple. |
| `attack_time_episode_count_gap_gt_1s (time level)` | 1 + number of gaps > 1.0 s between consecutive `attack=1` frames (threshold fixed in advance). `attack_time_contiguity_gap_gt_1s` = none / single_window / multiple_windows. |
| `attack_row_density_within_span` | attack1_count / (last_attack_row − first_attack_row + 1). |
| `quoted_row_count` | Rows containing a double-quote character. |

## D. Schema-integrity report

- CSVs whose header is exactly `timestamp,arbitration_id,data_field,attack` (no BOM): **236 / 236**.
- Distinct header variants observed: **1** → `timestamp,arbitration_id,data_field,attack` ×236
- Files with UTF-8 BOM: **0**.
- Rows with wrong field count: **0** · bad timestamp: **0** · bad arbitration_id: **0** · bad data_field: **1** · bad attack label: **0** · total malformed rows: **1** of 193,240,845.
- Blank lines: **0** · rows containing quotes: **0** · files not ending in newline: **0**.
- arbitration_id hex length (min,max) across files: ('3', '3') ×236.
- data_field hex length (min,max) across files: ('0', '16') ×39, ('0', '17') ×1, ('2', '16') ×112, ('4', '16') ×84 · odd-length payload rows: **1**.

Files failing schema or containing malformed rows:

| File | Header | Malformed | wrong-fields | bad ts | bad id | bad data | bad label |
|---|---|---:|---:|---:|---:|---:|---:|
| set_03/train_01/fuzzing-3.csv | `timestamp,arbitration_id,data_field,attack` | 1 | 0 | 0 | 0 | 1 | 0 |

## B. Exact-duplicate report (SHA-256)

- Total CSVs: **236** · distinct SHA-256: **174** · SHA-256 values occurring >1×: **62** · files involved: **124**.
- Total bytes: 7,471,443,340 · bytes of distinct content: 5,410,927,099 · total rows: 193,240,845 · rows of distinct content: 140,162,276.
- Multiplicity: 2 copies ×62.

| # | SHA-256 (first 16) | Rows | attack=1 | Occurrences (set / subset / file) |
|---:|---|---:|---:|---|
| 1 | `543c7f0f3218657a` | 1,100,971 | 157,652 | set_01 / test_02_unknown_vehicle_known_attack / DoS-3.csv<br>set_03 / train_01 / DoS-3.csv |
| 2 | `2f059858b0b25520` | 689,028 | 5,924 | set_01 / test_02_unknown_vehicle_known_attack / DoS-4.csv<br>set_03 / train_01 / DoS-4.csv |
| 3 | `be45ea3adc7dc010` | 449,461 | 32 | set_01 / test_02_unknown_vehicle_known_attack / force-neutral-3.csv<br>set_03 / train_01 / force-neutral-3.csv |
| 4 | `2b7b9c19741b51cf` | 1,646,238 | 56 | set_01 / test_02_unknown_vehicle_known_attack / force-neutral-4.csv<br>set_03 / train_01 / force-neutral-4.csv |
| 5 | `3d24a7fc708ca920` | 1,106,909 | 1,276 | set_01 / test_04_unknown_vehicle_unknown_attack / double-3.csv<br>set_02 / test_01_known_vehicle_known_attack / double-3.csv |
| 6 | `9e6248652f95b208` | 1,300,435 | 615 | set_01 / test_04_unknown_vehicle_unknown_attack / double-4.csv<br>set_02 / test_01_known_vehicle_known_attack / double-4.csv |
| 7 | `5e3f3d75efff9a7f` | 495,332 | 6,112 | set_01 / test_04_unknown_vehicle_unknown_attack / fuzzing-3.csv<br>set_02 / test_01_known_vehicle_known_attack / fuzzing-3.csv |
| 8 | `af823272547f3356` | 619,269 | 203 | set_01 / test_04_unknown_vehicle_unknown_attack / fuzzing-4.csv<br>set_02 / test_01_known_vehicle_known_attack / fuzzing-4.csv |
| 9 | `1d15c1d078fe7bc9` | 891,053 | 107 | set_01 / test_04_unknown_vehicle_unknown_attack / interval-3.csv<br>set_02 / test_01_known_vehicle_known_attack / interval-3.csv |
| 10 | `07d8e41c9554c95a` | 857,658 | 26 | set_01 / test_04_unknown_vehicle_unknown_attack / interval-4.csv<br>set_02 / test_01_known_vehicle_known_attack / interval-4.csv |
| 11 | `0925bcd53d764a4a` | 2,625,443 | 3,141 | set_01 / test_04_unknown_vehicle_unknown_attack / speed-3.csv<br>set_02 / test_01_known_vehicle_known_attack / speed-3.csv |
| 12 | `122cfd410b0d2b4b` | 1,898,360 | 64 | set_01 / test_04_unknown_vehicle_unknown_attack / speed-4.csv<br>set_02 / test_01_known_vehicle_known_attack / speed-4.csv |
| 13 | `bb4af22be82a9cc5` | 507,374 | 59 | set_01 / test_04_unknown_vehicle_unknown_attack / systematic-3.csv<br>set_02 / test_01_known_vehicle_known_attack / systematic-3.csv |
| 14 | `0687f61bf1c5093f` | 330,614 | 922 | set_01 / test_04_unknown_vehicle_unknown_attack / systematic-4.csv<br>set_02 / test_01_known_vehicle_known_attack / systematic-4.csv |
| 15 | `690d047141c7918b` | 1,993,660 | 606 | set_01 / test_04_unknown_vehicle_unknown_attack / triple-3.csv<br>set_02 / test_01_known_vehicle_known_attack / triple-3.csv |
| 16 | `122c3d6aebe4babc` | 594,448 | 1,113 | set_01 / test_04_unknown_vehicle_unknown_attack / triple-4.csv<br>set_02 / test_01_known_vehicle_known_attack / triple-4.csv |
| 17 | `b17052b50df3d363` | 393,679 | 788 | set_02 / test_02_unknown_vehicle_known_attack / interval-3.csv<br>set_04 / train_01 / interval-3.csv |
| 18 | `f5065b7a46575edf` | 907,454 | 250 | set_02 / test_02_unknown_vehicle_known_attack / interval-4.csv<br>set_04 / train_01 / interval-4.csv |
| 19 | `19eb55a1177d2ed8` | 649,177 | 333 | set_02 / test_02_unknown_vehicle_known_attack / speed-3.csv<br>set_04 / train_01 / speed-3.csv |
| 20 | `8bef72a087b488cb` | 486,777 | 334 | set_02 / test_02_unknown_vehicle_known_attack / speed-4.csv<br>set_04 / train_01 / speed-4.csv |
| 21 | `ae04b96d563258dc` | 1,012,913 | 9,774 | set_02 / test_02_unknown_vehicle_known_attack / systematic-3.csv<br>set_04 / train_01 / systematic-3.csv |
| 22 | `6e7adccb007a15c7` | 1,235,881 | 2,205 | set_02 / test_02_unknown_vehicle_known_attack / systematic-4.csv<br>set_04 / train_01 / systematic-4.csv |
| 23 | `3e14a91556ab1061` | 689,308 | 566 | set_02 / test_04_unknown_vehicle_unknown_attack / rpm-3.csv<br>set_04 / train_01 / rpm-3.csv |
| 24 | `d456f171549ddba8` | 642,822 | 880 | set_02 / test_04_unknown_vehicle_unknown_attack / rpm-4.csv<br>set_04 / train_01 / rpm-4.csv |
| 25 | `e5413befc9689c04` | 810,295 | 513 | set_02 / test_04_unknown_vehicle_unknown_attack / standstill-3.csv<br>set_04 / train_01 / standstill-3.csv |
| 26 | `df9c4d58bad77f8a` | 352,661 | 72 | set_02 / test_04_unknown_vehicle_unknown_attack / standstill-4.csv<br>set_04 / train_01 / standstill-4.csv |
| 27 | `70bb4ce03b30e2d7` | 1,092,582 | 4,955 | set_02 / train_01 / double-1.csv<br>set_04 / test_04_unknown_vehicle_unknown_attack / double-1.csv |
| 28 | `9e8b61b1097be54d` | 463,001 | 8,900 | set_02 / train_01 / double-2.csv<br>set_04 / test_04_unknown_vehicle_unknown_attack / double-2.csv |
| 29 | `e6d2f8117c1d59d9` | 1,235,992 | 113,514 | set_02 / train_01 / fuzzing-1.csv<br>set_04 / test_04_unknown_vehicle_unknown_attack / fuzzing-1.csv |
| 30 | `b9c68d608824c732` | 1,167,769 | 6,113 | set_02 / train_01 / fuzzing-2.csv<br>set_04 / test_04_unknown_vehicle_unknown_attack / fuzzing-2.csv |
| 31 | `eac9c98a5be612bb` | 634,191 | 15,125 | set_02 / train_01 / interval-1.csv<br>set_04 / test_02_unknown_vehicle_known_attack / interval-1.csv |
| 32 | `f8cc87d7bb869037` | 1,653,840 | 1,179 | set_02 / train_01 / interval-2.csv<br>set_04 / test_02_unknown_vehicle_known_attack / interval-2.csv |
| 33 | `0479e4b539c33b40` | 2,619,677 | 14 | set_02 / train_01 / speed-1.csv<br>set_04 / test_02_unknown_vehicle_known_attack / speed-1.csv |
| 34 | `a2f91f422d35cdda` | 2,734,513 | 38 | set_02 / train_01 / speed-2.csv<br>set_04 / test_02_unknown_vehicle_known_attack / speed-2.csv |
| 35 | `d88b9fdef1de156d` | 541,323 | 37,125 | set_02 / train_01 / systematic-1.csv<br>set_04 / test_02_unknown_vehicle_known_attack / systematic-1.csv |
| 36 | `4cda452db291be61` | 456,086 | 2,259 | set_02 / train_01 / systematic-2.csv<br>set_04 / test_02_unknown_vehicle_known_attack / systematic-2.csv |
| 37 | `b0416e85aee36c02` | 1,780,543 | 31,056 | set_02 / train_01 / triple-1.csv<br>set_04 / test_04_unknown_vehicle_unknown_attack / triple-1.csv |
| 38 | `c77c613f5b496514` | 661,579 | 4,059 | set_02 / train_01 / triple-2.csv<br>set_04 / test_04_unknown_vehicle_unknown_attack / triple-2.csv |
| 39 | `ba70baaa2e7eae05` | 643,807 | 12,091 | set_03 / test_02_unknown_vehicle_known_attack / DoS-1.csv<br>set_04 / test_03_known_vehicle_unknown_attack / DoS-1.csv |
| 40 | `8ac793414409eff6` | 709,039 | 25,308 | set_03 / test_02_unknown_vehicle_known_attack / DoS-2.csv<br>set_04 / test_03_known_vehicle_unknown_attack / DoS-2.csv |
| 41 | `cb6e794a3de531e7` | 1,244,063 | 10,387 | set_03 / test_02_unknown_vehicle_known_attack / double-1.csv<br>set_04 / test_03_known_vehicle_unknown_attack / double-1.csv |
| 42 | `c592898c200fc387` | 695,540 | 4,614 | set_03 / test_02_unknown_vehicle_known_attack / double-2.csv<br>set_04 / test_03_known_vehicle_unknown_attack / double-2.csv |
| 43 | `c1a10149201f802a` | 527,589 | 1,720 | set_03 / test_02_unknown_vehicle_known_attack / force-neutral-1.csv<br>set_04 / test_03_known_vehicle_unknown_attack / force-neutral-1.csv |
| 44 | `c24ae73768ef703f` | 475,757 | 1,379 | set_03 / test_02_unknown_vehicle_known_attack / force-neutral-2.csv<br>set_04 / test_03_known_vehicle_unknown_attack / force-neutral-2.csv |
| 45 | `4d3db9215b3a76c6` | 660,170 | 28,454 | set_03 / test_02_unknown_vehicle_known_attack / fuzzing-1.csv<br>set_04 / test_03_known_vehicle_unknown_attack / fuzzing-1.csv |
| 46 | `00c41be1a38f99d3` | 650,196 | 6,557 | set_03 / test_02_unknown_vehicle_known_attack / fuzzing-2.csv<br>set_04 / test_03_known_vehicle_unknown_attack / fuzzing-2.csv |
| 47 | `a20dca9b3342ffcc` | 544,385 | 52,917 | set_03 / test_02_unknown_vehicle_known_attack / triple-1.csv<br>set_04 / test_03_known_vehicle_unknown_attack / triple-1.csv |
| 48 | `3d46aaada8ed35e5` | 703,688 | 12,762 | set_03 / test_02_unknown_vehicle_known_attack / triple-2.csv<br>set_04 / test_03_known_vehicle_unknown_attack / triple-2.csv |
| 49 | `bae034158b49ac5d` | 857,154 | 91,684 | set_03 / test_04_unknown_vehicle_unknown_attack / interval-1.csv<br>set_04 / test_01_known_vehicle_known_attack / interval-1.csv |
| 50 | `4c0d7fd5fabc804d` | 465,145 | 13,592 | set_03 / test_04_unknown_vehicle_unknown_attack / interval-2.csv<br>set_04 / test_01_known_vehicle_known_attack / interval-2.csv |
| 51 | `ed1de9001aadceb8` | 488,528 | 4,830 | set_03 / test_04_unknown_vehicle_unknown_attack / rpm-1.csv<br>set_04 / test_01_known_vehicle_known_attack / rpm-1.csv |
| 52 | `8d69e9a2f72ded99` | 569,888 | 468 | set_03 / test_04_unknown_vehicle_unknown_attack / rpm-2.csv<br>set_04 / test_01_known_vehicle_known_attack / rpm-2.csv |
| 53 | `0b2cd22e6efa958e` | 129,817 | 1,348 | set_03 / test_04_unknown_vehicle_unknown_attack / rpm-accessory-1.csv<br>set_04 / test_01_known_vehicle_known_attack / rpm-accessory-1.csv |
| 54 | `f7ff3cd2997991fb` | 138,381 | 215 | set_03 / test_04_unknown_vehicle_unknown_attack / rpm-accessory-2.csv<br>set_04 / test_01_known_vehicle_known_attack / rpm-accessory-2.csv |
| 55 | `7b9b7973e083836d` | 757,055 | 12,875 | set_03 / test_04_unknown_vehicle_unknown_attack / speed-1.csv<br>set_04 / test_01_known_vehicle_known_attack / speed-1.csv |
| 56 | `34dc42612af9a773` | 714,871 | 1,358 | set_03 / test_04_unknown_vehicle_unknown_attack / speed-2.csv<br>set_04 / test_01_known_vehicle_known_attack / speed-2.csv |
| 57 | `ff264d1b07da2d34` | 262,041 | 1,430 | set_03 / test_04_unknown_vehicle_unknown_attack / speed-accessory-1.csv<br>set_04 / test_01_known_vehicle_known_attack / speed-accessory-1.csv |
| 58 | `55b79b9c9493ce35` | 164,771 | 90 | set_03 / test_04_unknown_vehicle_unknown_attack / speed-accessory-2.csv<br>set_04 / test_01_known_vehicle_known_attack / speed-accessory-2.csv |
| 59 | `15926e6cb364f9e1` | 306,189 | 7,862 | set_03 / test_04_unknown_vehicle_unknown_attack / standstill-1.csv<br>set_04 / test_01_known_vehicle_known_attack / standstill-1.csv |
| 60 | `7dbd5df9d928149f` | 892,327 | 2,361 | set_03 / test_04_unknown_vehicle_unknown_attack / standstill-2.csv<br>set_04 / test_01_known_vehicle_known_attack / standstill-2.csv |
| 61 | `fe44285f29d4d59d` | 519,433 | 9,468 | set_03 / test_04_unknown_vehicle_unknown_attack / systematic-1.csv<br>set_04 / test_01_known_vehicle_known_attack / systematic-1.csv |
| 62 | `7f1cdfd5af58d2fb` | 630,419 | 2,367 | set_03 / test_04_unknown_vehicle_unknown_attack / systematic-2.csv<br>set_04 / test_01_known_vehicle_known_attack / systematic-2.csv |

- Same filename + same size but different SHA-256: **0**.
- Same SHA-256 under different filenames: **0**.
- Same SHA-256 within the same set (any subsets): **0**.

## C. Cross-set train/test leakage report (same SHA-256)

Definition applied: a SHA-256 that occurs in a `train_01` partition of one set AND in a `test_0*` partition of a different set.

- Leakage pairs found: **26** (distinct SHA-256: **26**).
- Same SHA-256 in train and test of the **same** set: **0**.

| # | Train occurrence | Test occurrence | SHA-256 (first 16) | Rows | attack=1 |
|---:|---|---|---|---:|---:|
| 1 | set_02/train_01/interval-1.csv | set_04/test_02_unknown_vehicle_known_attack/interval-1.csv | `eac9c98a5be612bb` | 634,191 | 15,125 |
| 2 | set_02/train_01/interval-2.csv | set_04/test_02_unknown_vehicle_known_attack/interval-2.csv | `f8cc87d7bb869037` | 1,653,840 | 1,179 |
| 3 | set_02/train_01/speed-1.csv | set_04/test_02_unknown_vehicle_known_attack/speed-1.csv | `0479e4b539c33b40` | 2,619,677 | 14 |
| 4 | set_02/train_01/speed-2.csv | set_04/test_02_unknown_vehicle_known_attack/speed-2.csv | `a2f91f422d35cdda` | 2,734,513 | 38 |
| 5 | set_02/train_01/systematic-1.csv | set_04/test_02_unknown_vehicle_known_attack/systematic-1.csv | `d88b9fdef1de156d` | 541,323 | 37,125 |
| 6 | set_02/train_01/systematic-2.csv | set_04/test_02_unknown_vehicle_known_attack/systematic-2.csv | `4cda452db291be61` | 456,086 | 2,259 |
| 7 | set_02/train_01/double-1.csv | set_04/test_04_unknown_vehicle_unknown_attack/double-1.csv | `70bb4ce03b30e2d7` | 1,092,582 | 4,955 |
| 8 | set_02/train_01/double-2.csv | set_04/test_04_unknown_vehicle_unknown_attack/double-2.csv | `9e8b61b1097be54d` | 463,001 | 8,900 |
| 9 | set_02/train_01/fuzzing-1.csv | set_04/test_04_unknown_vehicle_unknown_attack/fuzzing-1.csv | `e6d2f8117c1d59d9` | 1,235,992 | 113,514 |
| 10 | set_02/train_01/fuzzing-2.csv | set_04/test_04_unknown_vehicle_unknown_attack/fuzzing-2.csv | `b9c68d608824c732` | 1,167,769 | 6,113 |
| 11 | set_02/train_01/triple-1.csv | set_04/test_04_unknown_vehicle_unknown_attack/triple-1.csv | `b0416e85aee36c02` | 1,780,543 | 31,056 |
| 12 | set_02/train_01/triple-2.csv | set_04/test_04_unknown_vehicle_unknown_attack/triple-2.csv | `c77c613f5b496514` | 661,579 | 4,059 |
| 13 | set_03/train_01/DoS-3.csv | set_01/test_02_unknown_vehicle_known_attack/DoS-3.csv | `543c7f0f3218657a` | 1,100,971 | 157,652 |
| 14 | set_03/train_01/DoS-4.csv | set_01/test_02_unknown_vehicle_known_attack/DoS-4.csv | `2f059858b0b25520` | 689,028 | 5,924 |
| 15 | set_03/train_01/force-neutral-3.csv | set_01/test_02_unknown_vehicle_known_attack/force-neutral-3.csv | `be45ea3adc7dc010` | 449,461 | 32 |
| 16 | set_03/train_01/force-neutral-4.csv | set_01/test_02_unknown_vehicle_known_attack/force-neutral-4.csv | `2b7b9c19741b51cf` | 1,646,238 | 56 |
| 17 | set_04/train_01/interval-3.csv | set_02/test_02_unknown_vehicle_known_attack/interval-3.csv | `b17052b50df3d363` | 393,679 | 788 |
| 18 | set_04/train_01/interval-4.csv | set_02/test_02_unknown_vehicle_known_attack/interval-4.csv | `f5065b7a46575edf` | 907,454 | 250 |
| 19 | set_04/train_01/speed-3.csv | set_02/test_02_unknown_vehicle_known_attack/speed-3.csv | `19eb55a1177d2ed8` | 649,177 | 333 |
| 20 | set_04/train_01/speed-4.csv | set_02/test_02_unknown_vehicle_known_attack/speed-4.csv | `8bef72a087b488cb` | 486,777 | 334 |
| 21 | set_04/train_01/systematic-3.csv | set_02/test_02_unknown_vehicle_known_attack/systematic-3.csv | `ae04b96d563258dc` | 1,012,913 | 9,774 |
| 22 | set_04/train_01/systematic-4.csv | set_02/test_02_unknown_vehicle_known_attack/systematic-4.csv | `6e7adccb007a15c7` | 1,235,881 | 2,205 |
| 23 | set_04/train_01/rpm-3.csv | set_02/test_04_unknown_vehicle_unknown_attack/rpm-3.csv | `3e14a91556ab1061` | 689,308 | 566 |
| 24 | set_04/train_01/rpm-4.csv | set_02/test_04_unknown_vehicle_unknown_attack/rpm-4.csv | `d456f171549ddba8` | 642,822 | 880 |
| 25 | set_04/train_01/standstill-3.csv | set_02/test_04_unknown_vehicle_unknown_attack/standstill-3.csv | `e5413befc9689c04` | 810,295 | 513 |
| 26 | set_04/train_01/standstill-4.csv | set_02/test_04_unknown_vehicle_unknown_attack/standstill-4.csv | `df9c4d58bad77f8a` | 352,661 | 72 |

Summary by (train set → test set/subset):

| Train set | Test set | Test subset | Files |
|---|---|---|---:|
| set_02 | set_04 | test_02_unknown_vehicle_known_attack | 6 |
| set_02 | set_04 | test_04_unknown_vehicle_unknown_attack | 6 |
| set_03 | set_01 | test_02_unknown_vehicle_known_attack | 4 |
| set_04 | set_02 | test_02_unknown_vehicle_known_attack | 6 |
| set_04 | set_02 | test_04_unknown_vehicle_unknown_attack | 4 |

For completeness (not train/test leakage by the definition above): same SHA-256 in test partitions of two different sets: **36** pairs; in train partitions of two different sets: **0** pairs.

## E. Class-imbalance summary by set and subset

| Set | Subset | Files | Rows | attack=0 | attack=1 | attack ratio | min file ratio | max file ratio | files with 0 attacks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| set_01 | test_01_known_vehicle_known_attack | 8 | 5,702,670 | 5,639,390 | 63,280 | 0.01110 | 0.00008 | 0.12462 | 0 |
| set_01 | test_02_unknown_vehicle_known_attack | 8 | 6,447,917 | 6,283,750 | 164,167 | 0.02546 | 0.00003 | 0.14319 | 0 |
| set_01 | test_03_known_vehicle_unknown_attack | 12 | 8,635,275 | 8,614,450 | 20,825 | 0.00241 | 0.00009 | 0.01035 | 0 |
| set_01 | test_04_unknown_vehicle_unknown_attack | 12 | 13,220,555 | 13,206,311 | 14,244 | 0.00108 | 0.00003 | 0.01234 | 0 |
| set_01 | train_01 | 12 | 10,653,140 | 10,603,583 | 49,557 | 0.00465 | 0.00000 | 0.10135 | 4 |
| set_02 | test_01_known_vehicle_known_attack | 12 | 13,220,555 | 13,206,311 | 14,244 | 0.00108 | 0.00003 | 0.01234 | 0 |
| set_02 | test_02_unknown_vehicle_known_attack | 12 | 8,445,427 | 8,425,378 | 20,049 | 0.00237 | 0.00020 | 0.00965 | 0 |
| set_02 | test_03_known_vehicle_unknown_attack | 8 | 12,150,056 | 12,121,265 | 28,791 | 0.00237 | 0.00001 | 0.02894 | 0 |
| set_02 | test_04_unknown_vehicle_unknown_attack | 8 | 4,789,904 | 4,771,896 | 18,008 | 0.00376 | 0.00020 | 0.01567 | 0 |
| set_02 | train_01 | 16 | 17,340,810 | 17,116,473 | 224,337 | 0.01294 | 0.00000 | 0.09184 | 4 |
| set_03 | test_01_known_vehicle_known_attack | 10 | 8,575,791 | 8,413,286 | 162,505 | 0.01895 | 0.00070 | 0.17326 | 0 |
| set_03 | test_02_unknown_vehicle_known_attack | 10 | 6,854,234 | 6,698,045 | 156,189 | 0.02279 | 0.00290 | 0.09721 | 0 |
| set_03 | test_03_known_vehicle_unknown_attack | 14 | 9,447,951 | 9,429,799 | 18,152 | 0.00192 | 0.00017 | 0.02340 | 0 |
| set_03 | test_04_unknown_vehicle_unknown_attack | 14 | 6,896,019 | 6,746,071 | 149,948 | 0.02174 | 0.00055 | 0.10696 | 0 |
| set_03 | train_01 | 14 | 12,025,767 | 11,856,088 | 169,679 | 0.01411 | 0.00000 | 0.14319 | 4 |
| set_04 | test_01_known_vehicle_known_attack | 14 | 6,896,019 | 6,746,071 | 149,948 | 0.02174 | 0.00055 | 0.10696 | 0 |
| set_04 | test_02_unknown_vehicle_known_attack | 14 | 17,408,094 | 17,350,855 | 57,239 | 0.00329 | 0.00001 | 0.06858 | 0 |
| set_04 | test_03_known_vehicle_unknown_attack | 10 | 6,854,234 | 6,698,045 | 156,189 | 0.02279 | 0.00290 | 0.09721 | 0 |
| set_04 | test_04_unknown_vehicle_unknown_attack | 10 | 8,183,626 | 7,962,655 | 220,971 | 0.02700 | 0.00000 | 0.09184 | 1 |
| set_04 | train_01 | 18 | 9,492,801 | 9,466,722 | 26,079 | 0.00275 | 0.00000 | 0.04738 | 4 |
| **All** | (with duplicates) | 236 | 193,240,845 | 191,356,444 | 1,884,401 | 0.00975 | | | 17 |
| **All** | (distinct SHA-256 only) | 174 | 140,162,276 | 139,001,972 | 1,160,304 | 0.00828 | | | |

By attack-family token (distinct SHA-256 only):

| Token | Distinct files | Rows | attack=1 | ratio | min file ratio | max file ratio |
|---|---:|---:|---:|---:|---:|---:|
| accessory | 8 | 2,018,077 | 0 | 0.00000 | 0.00000 | 0.00000 |
| attack-free | 8 | 8,944,853 | 0 | 0.00000 | 0.00000 | 0.00000 |
| DoS | 16 | 8,573,794 | 483,764 | 0.05642 | 0.00860 | 0.17326 |
| double | 14 | 13,230,777 | 41,376 | 0.00313 | 0.00022 | 0.01922 |
| force-neutral | 16 | 17,913,670 | 19,148 | 0.00107 | 0.00000 | 0.00909 |
| fuzzing | 14 | 9,896,488 | 224,403 | 0.02268 | 0.00009 | 0.09184 |
| interval | 12 | 10,291,241 | 135,139 | 0.01313 | 0.00003 | 0.10696 |
| rpm | 16 | 16,214,285 | 16,811 | 0.00104 | 0.00001 | 0.00989 |
| rpm-accessory | 8 | 1,753,769 | 10,487 | 0.00598 | 0.00017 | 0.04738 |
| speed | 12 | 15,914,455 | 24,902 | 0.00156 | 0.00001 | 0.01701 |
| speed-accessory | 8 | 2,221,050 | 7,524 | 0.00339 | 0.00003 | 0.02340 |
| standstill | 16 | 13,090,088 | 19,130 | 0.00146 | 0.00001 | 0.02568 |
| systematic | 12 | 7,928,615 | 65,970 | 0.00832 | 0.00012 | 0.06858 |
| triple | 14 | 12,171,114 | 111,650 | 0.00917 | 0.00020 | 0.09721 |

## F. Anomalies that could affect experimental validity (reported, not interpreted)

1. **Exact duplicate files:** 124 of 236 CSVs belong to 62 SHA-256 groups (§B).
2. **Cross-set train↔test identity:** 26 train/test file pairs across different sets share a SHA-256 (§C).
3. **Files with zero attack frames:** 17 — set_01/train_01/accessory-1.csv, set_01/train_01/accessory-2.csv, set_01/train_01/attack-free-1.csv, set_01/train_01/attack-free-2.csv, set_02/train_01/accessory-1.csv, set_02/train_01/accessory-2.csv, set_02/train_01/attack-free-1.csv, set_02/train_01/attack-free-2.csv, set_03/train_01/accessory-3.csv, set_03/train_01/accessory-4.csv, set_03/train_01/attack-free-3.csv, set_03/train_01/attack-free-4.csv, set_04/test_04_unknown_vehicle_unknown_attack/force-neutral-2.csv, set_04/train_01/accessory-3.csv, set_04/train_01/accessory-4.csv, set_04/train_01/attack-free-3.csv, set_04/train_01/attack-free-4.csv.
4. **Files named `attack-free`/`accessory` that contain attack=1 rows:** 0.
5. **Non-monotonic timestamps:** 100 files, 12,527 decreases in total; largest single decrease 0.007894993 s. Files: set_02/train_01/interval-1.csv (3424, max 0.005339s), set_04/test_02_unknown_vehicle_known_attack/interval-1.csv (3424, max 0.005339s), set_03/test_02_unknown_vehicle_known_attack/triple-1.csv (821, max 0.000591s), set_04/test_03_known_vehicle_unknown_attack/triple-1.csv (821, max 0.000591s), set_02/train_01/triple-1.csv (355, max 0.005810s), set_04/test_04_unknown_vehicle_unknown_attack/triple-1.csv (355, max 0.005810s), set_03/test_02_unknown_vehicle_known_attack/triple-2.csv (202, max 0.000160s), set_04/test_03_known_vehicle_unknown_attack/triple-2.csv (202, max 0.000160s), set_03/test_02_unknown_vehicle_known_attack/double-1.csv (197, max 0.000199s), set_04/test_03_known_vehicle_unknown_attack/double-1.csv (197, max 0.000199s), set_02/test_02_unknown_vehicle_known_attack/double-3.csv (147, max 0.000134s), set_01/train_01/force-neutral-1.csv (142, max 0.007418s), set_01/test_01_known_vehicle_known_attack/rpm-3.csv (100, max 0.000147s), set_03/test_02_unknown_vehicle_known_attack/double-2.csv (87, max 0.000445s), set_04/test_03_known_vehicle_unknown_attack/double-2.csv (87, max 0.000445s), set_02/train_01/double-2.csv (82, max 0.000126s), set_04/test_04_unknown_vehicle_unknown_attack/double-2.csv (82, max 0.000126s), set_02/train_01/double-1.csv (73, max 0.000124s), set_04/test_04_unknown_vehicle_unknown_attack/double-1.csv (73, max 0.000124s), set_02/train_01/interval-2.csv (71, max 0.000104s), set_04/test_02_unknown_vehicle_known_attack/interval-2.csv (71, max 0.000104s), set_03/test_01_known_vehicle_known_attack/force-neutral-1.csv (64, max 0.000163s), set_02/train_01/triple-2.csv (62, max 0.000149s), set_04/test_04_unknown_vehicle_unknown_attack/triple-2.csv (62, max 0.000149s), set_03/test_01_known_vehicle_known_attack/double-1.csv (60, max 0.000152s), set_01/test_01_known_vehicle_known_attack/standstill-3.csv (59, max 0.002910s), set_03/test_03_known_vehicle_unknown_attack/speed-accessory-1.csv (55, max 0.000084s), set_01/test_01_known_vehicle_known_attack/force-neutral-3.csv (50, max 0.000134s), set_01/test_03_known_vehicle_unknown_attack/triple-3.csv (50, max 0.000155s), set_01/test_04_unknown_vehicle_unknown_attack/speed-3.csv (45, max 0.000179s), set_02/test_01_known_vehicle_known_attack/speed-3.csv (45, max 0.000179s), set_01/train_01/rpm-1.csv (41, max 0.000127s), set_03/test_01_known_vehicle_known_attack/triple-2.csv (38, max 0.000133s), set_01/test_03_known_vehicle_unknown_attack/speed-3.csv (36, max 0.000022s), set_03/test_03_known_vehicle_unknown_attack/standstill-1.csv (36, max 0.000030s), set_01/test_03_known_vehicle_unknown_attack/double-3.csv (33, max 0.000114s), set_03/test_03_known_vehicle_unknown_attack/rpm-1.csv (32, max 0.000077s), set_04/train_01/speed-accessory-4.csv (32, max 0.000109s), set_01/test_03_known_vehicle_unknown_attack/double-4.csv (31, max 0.000076s), set_02/test_03_known_vehicle_unknown_attack/DoS-3.csv (31, max 0.000005s), set_03/test_01_known_vehicle_known_attack/force-neutral-2.csv (31, max 0.000130s), set_02/test_02_unknown_vehicle_known_attack/double-4.csv (30, max 0.000155s), set_03/test_01_known_vehicle_known_attack/double-2.csv (28, max 0.000172s), set_03/test_01_known_vehicle_known_attack/triple-1.csv (28, max 0.000282s), set_01/train_01/force-neutral-2.csv (25, max 0.000120s), set_01/train_01/standstill-1.csv (25, max 0.000169s), set_01/train_01/standstill-2.csv (24, max 0.007895s), set_01/test_04_unknown_vehicle_unknown_attack/triple-4.csv (22, max 0.000110s), set_02/test_01_known_vehicle_known_attack/triple-4.csv (22, max 0.000110s), set_03/test_03_known_vehicle_unknown_attack/rpm-2.csv (20, max 0.000123s), set_01/train_01/rpm-2.csv (19, max 0.000111s), set_03/test_03_known_vehicle_unknown_attack/speed-2.csv (19, max 0.000147s), set_04/test_02_unknown_vehicle_known_attack/rpm-1.csv (19, max 0.000080s), set_04/test_04_unknown_vehicle_unknown_attack/force-neutral-1.csv (19, max 0.000050s), set_04/test_02_unknown_vehicle_known_attack/standstill-1.csv (18, max 0.000106s), set_01/test_03_known_vehicle_unknown_attack/speed-4.csv (16, max 0.000048s), set_01/test_04_unknown_vehicle_unknown_attack/double-3.csv (15, max 0.000055s), set_02/test_01_known_vehicle_known_attack/double-3.csv (15, max 0.000055s), set_01/test_03_known_vehicle_unknown_attack/triple-4.csv (14, max 0.000101s), set_03/test_03_known_vehicle_unknown_attack/standstill-2.csv (14, max 0.000079s), set_03/train_01/triple-4.csv (14, max 0.000084s), set_03/test_03_known_vehicle_unknown_attack/speed-1.csv (12, max 0.000102s), set_01/test_02_unknown_vehicle_known_attack/standstill-3.csv (10, max 0.000155s), set_01/test_04_unknown_vehicle_unknown_attack/triple-3.csv (10, max 0.000146s), set_02/test_01_known_vehicle_known_attack/triple-3.csv (10, max 0.000146s), set_03/train_01/triple-3.csv (10, max 0.000095s), set_04/test_02_unknown_vehicle_known_attack/rpm-accessory-1.csv (10, max 0.000084s), set_01/test_01_known_vehicle_known_attack/force-neutral-4.csv (9, max 0.006043s), set_01/test_04_unknown_vehicle_unknown_attack/double-4.csv (9, max 0.000032s), set_02/test_01_known_vehicle_known_attack/double-4.csv (9, max 0.000032s), set_01/test_01_known_vehicle_known_attack/rpm-4.csv (8, max 0.000115s), set_02/test_02_unknown_vehicle_known_attack/triple-4.csv (8, max 0.000087s), set_02/test_03_known_vehicle_unknown_attack/force-neutral-4.csv (7, max 0.000084s), set_03/train_01/double-3.csv (7, max 0.000079s), set_01/test_04_unknown_vehicle_unknown_attack/speed-4.csv (6, max 0.000036s), set_02/test_01_known_vehicle_known_attack/speed-4.csv (6, max 0.000036s), set_02/train_01/speed-1.csv (6, max 0.000067s), set_02/train_01/speed-2.csv (6, max 0.000029s), set_04/test_02_unknown_vehicle_known_attack/speed-1.csv (6, max 0.000067s), set_04/test_02_unknown_vehicle_known_attack/speed-2.csv (6, max 0.000029s), set_01/test_02_unknown_vehicle_known_attack/force-neutral-4.csv (5, max 0.000058s), set_01/test_02_unknown_vehicle_known_attack/rpm-3.csv (5, max 0.000024s), set_02/test_02_unknown_vehicle_known_attack/triple-3.csv (5, max 0.000050s), set_03/test_03_known_vehicle_unknown_attack/speed-accessory-2.csv (5, max 0.000029s), set_03/train_01/force-neutral-4.csv (5, max 0.000058s), set_04/test_02_unknown_vehicle_known_attack/rpm-2.csv (5, max 0.000024s), set_03/train_01/double-4.csv (4, max 0.000061s), set_01/test_02_unknown_vehicle_known_attack/standstill-4.csv (3, max 0.000092s), set_02/test_03_known_vehicle_unknown_attack/force-neutral-3.csv (3, max 0.000038s), set_02/test_03_known_vehicle_unknown_attack/rpm-3.csv (3, max 0.000048s), set_02/test_03_known_vehicle_unknown_attack/rpm-4.csv (3, max 0.000110s), set_01/test_02_unknown_vehicle_known_attack/rpm-4.csv (2, max 0.000018s), set_02/test_03_known_vehicle_unknown_attack/standstill-3.csv (2, max 0.000130s), set_04/test_02_unknown_vehicle_known_attack/rpm-accessory-2.csv (2, max 0.000046s), set_04/test_02_unknown_vehicle_known_attack/speed-accessory-1.csv (2, max 0.000032s), set_04/test_02_unknown_vehicle_known_attack/standstill-2.csv (2, max 0.000019s), set_01/test_02_unknown_vehicle_known_attack/force-neutral-3.csv (1, max 0.000130s), set_03/test_03_known_vehicle_unknown_attack/rpm-accessory-1.csv (1, max 0.000032s), set_03/test_03_known_vehicle_unknown_attack/rpm-accessory-2.csv (1, max 0.000048s), set_03/train_01/force-neutral-3.csv (1, max 0.000130s)
6. **Equal consecutive timestamps:** 3,033 rows across 145 files.
7. **Timestamp origin:** distinct per-file minimum timestamps: 1 → `1672531200.0` ×236. Time spans range 48.0–2103.9 s.
8. **Empty data_field:** 32,378 rows in 40 files; of these 32,378 are attack=1. Files: set_01/test_03_known_vehicle_unknown_attack/fuzzing-3.csv (385/385 attack), set_01/test_03_known_vehicle_unknown_attack/fuzzing-4.csv (1/1 attack), set_01/test_03_known_vehicle_unknown_attack/systematic-3.csv (67/67 attack), set_01/test_03_known_vehicle_unknown_attack/systematic-4.csv (17/17 attack), set_01/test_04_unknown_vehicle_unknown_attack/fuzzing-3.csv (370/370 attack), set_01/test_04_unknown_vehicle_unknown_attack/fuzzing-4.csv (10/10 attack), set_01/test_04_unknown_vehicle_unknown_attack/systematic-3.csv (4/4 attack), set_01/test_04_unknown_vehicle_unknown_attack/systematic-4.csv (61/61 attack), set_02/test_01_known_vehicle_known_attack/fuzzing-3.csv (370/370 attack), set_02/test_01_known_vehicle_known_attack/fuzzing-4.csv (10/10 attack), set_02/test_01_known_vehicle_known_attack/systematic-3.csv (4/4 attack), set_02/test_01_known_vehicle_known_attack/systematic-4.csv (61/61 attack), set_02/test_02_unknown_vehicle_known_attack/fuzzing-3.csv (57/57 attack), set_02/test_02_unknown_vehicle_known_attack/fuzzing-4.csv (70/70 attack), set_02/test_02_unknown_vehicle_known_attack/systematic-3.csv (605/605 attack), set_02/test_02_unknown_vehicle_known_attack/systematic-4.csv (131/131 attack), set_02/train_01/fuzzing-1.csv (7165/7165 attack), set_02/train_01/fuzzing-2.csv (359/359 attack), set_02/train_01/systematic-1.csv (2324/2324 attack), set_02/train_01/systematic-2.csv (134/134 attack), set_03/test_01_known_vehicle_known_attack/fuzzing-1.csv (3143/3143 attack), set_03/test_01_known_vehicle_known_attack/fuzzing-2.csv (27/27 attack), set_03/test_02_unknown_vehicle_known_attack/fuzzing-1.csv (1837/1837 attack), set_03/test_02_unknown_vehicle_known_attack/fuzzing-2.csv (434/434 attack), set_03/test_03_known_vehicle_unknown_attack/systematic-1.csv (30/30 attack), set_03/test_03_known_vehicle_unknown_attack/systematic-2.csv (12/12 attack), set_03/test_04_unknown_vehicle_unknown_attack/systematic-1.csv (567/567 attack), set_03/test_04_unknown_vehicle_unknown_attack/systematic-2.csv (159/159 attack), set_03/train_01/fuzzing-3.csv (237/237 attack), set_03/train_01/fuzzing-4.csv (12/12 attack), set_04/test_01_known_vehicle_known_attack/systematic-1.csv (567/567 attack), set_04/test_01_known_vehicle_known_attack/systematic-2.csv (159/159 attack), set_04/test_02_unknown_vehicle_known_attack/systematic-1.csv (2324/2324 attack), set_04/test_02_unknown_vehicle_known_attack/systematic-2.csv (134/134 attack), set_04/test_03_known_vehicle_unknown_attack/fuzzing-1.csv (1837/1837 attack), set_04/test_03_known_vehicle_unknown_attack/fuzzing-2.csv (434/434 attack), set_04/test_04_unknown_vehicle_unknown_attack/fuzzing-1.csv (7165/7165 attack), set_04/test_04_unknown_vehicle_unknown_attack/fuzzing-2.csv (359/359 attack), set_04/train_01/systematic-3.csv (605/605 attack), set_04/train_01/systematic-4.csv (131/131 attack)
9. **Attack contiguity (row level):** multiple ×219, none ×17. **(time level, gap > 1 s):** multiple_windows ×44, single_window ×175, none ×17.
10. **Files with multiple attack time-windows (gap > 1 s):** set_01/test_01_known_vehicle_known_attack/DoS-3.csv (3 windows, max gap 7.277s), set_01/test_01_known_vehicle_known_attack/DoS-4.csv (2 windows, max gap 7.381s), set_01/test_02_unknown_vehicle_known_attack/rpm-4.csv (26 windows, max gap 1.003s), set_01/test_03_known_vehicle_unknown_attack/fuzzing-4.csv (38 windows, max gap 1.000s), set_01/test_03_known_vehicle_unknown_attack/interval-3.csv (2 windows, max gap 60.176s), set_01/test_04_unknown_vehicle_unknown_attack/systematic-3.csv (59 windows, max gap 1.000s), set_01/test_04_unknown_vehicle_unknown_attack/systematic-4.csv (2 windows, max gap 34.901s), set_02/test_01_known_vehicle_known_attack/systematic-3.csv (59 windows, max gap 1.000s), set_02/test_01_known_vehicle_known_attack/systematic-4.csv (2 windows, max gap 34.901s), set_02/test_02_unknown_vehicle_known_attack/systematic-3.csv (4 windows, max gap 15.351s), set_02/test_03_known_vehicle_unknown_attack/force-neutral-4.csv (17 windows, max gap 10.832s), set_02/test_03_known_vehicle_unknown_attack/standstill-3.csv (6 windows, max gap 10.003s), set_02/test_03_known_vehicle_unknown_attack/standstill-4.csv (13 windows, max gap 3.003s), set_02/test_04_unknown_vehicle_unknown_attack/force-neutral-3.csv (4 windows, max gap 29.554s), set_02/test_04_unknown_vehicle_unknown_attack/rpm-4.csv (8 windows, max gap 6.255s), set_03/test_01_known_vehicle_known_attack/DoS-2.csv (2 windows, max gap 22.278s), set_03/test_01_known_vehicle_known_attack/force-neutral-1.csv (2 windows, max gap 27.203s), set_03/test_01_known_vehicle_known_attack/fuzzing-2.csv (5 windows, max gap 47.637s), set_03/test_02_unknown_vehicle_known_attack/DoS-2.csv (6 windows, max gap 67.509s), set_03/test_02_unknown_vehicle_known_attack/double-1.csv (3 windows, max gap 59.714s), set_03/test_02_unknown_vehicle_known_attack/fuzzing-1.csv (3 windows, max gap 96.077s), set_03/test_02_unknown_vehicle_known_attack/fuzzing-2.csv (2 windows, max gap 111.548s), set_03/test_02_unknown_vehicle_known_attack/triple-2.csv (3 windows, max gap 130.893s), set_03/test_03_known_vehicle_unknown_attack/interval-2.csv (6 windows, max gap 113.305s), set_03/test_03_known_vehicle_unknown_attack/rpm-accessory-1.csv (28 windows, max gap 1.004s), set_03/test_03_known_vehicle_unknown_attack/rpm-accessory-2.csv (30 windows, max gap 1.003s), set_03/test_04_unknown_vehicle_unknown_attack/rpm-1.csv (5 windows, max gap 56.282s), set_03/test_04_unknown_vehicle_unknown_attack/speed-1.csv (6 windows, max gap 99.589s), set_03/test_04_unknown_vehicle_unknown_attack/speed-2.csv (5 windows, max gap 88.671s), set_03/train_01/fuzzing-3.csv (2 windows, max gap 43.342s), set_04/test_01_known_vehicle_known_attack/rpm-1.csv (5 windows, max gap 56.282s), set_04/test_01_known_vehicle_known_attack/speed-1.csv (6 windows, max gap 99.589s), set_04/test_01_known_vehicle_known_attack/speed-2.csv (5 windows, max gap 88.671s), set_04/test_02_unknown_vehicle_known_attack/rpm-accessory-2.csv (2 windows, max gap 55.602s), set_04/test_02_unknown_vehicle_known_attack/speed-accessory-2.csv (10 windows, max gap 3.003s), set_04/test_02_unknown_vehicle_known_attack/standstill-1.csv (2 windows, max gap 187.332s), set_04/test_02_unknown_vehicle_known_attack/standstill-2.csv (24 windows, max gap 10.004s), set_04/test_03_known_vehicle_unknown_attack/DoS-2.csv (6 windows, max gap 67.509s), set_04/test_03_known_vehicle_unknown_attack/double-1.csv (3 windows, max gap 59.714s), set_04/test_03_known_vehicle_unknown_attack/fuzzing-1.csv (3 windows, max gap 96.077s), set_04/test_03_known_vehicle_unknown_attack/fuzzing-2.csv (2 windows, max gap 111.548s), set_04/test_03_known_vehicle_unknown_attack/triple-2.csv (3 windows, max gap 130.893s), set_04/train_01/rpm-4.csv (8 windows, max gap 6.255s), set_04/train_01/systematic-3.csv (4 windows, max gap 15.351s).
11. **Odd-length hex payloads:** 1 rows in 1 files.
12. **Stage 1 correction:** Stage 1 stated that attack frames form a single contiguous block. At row level this is not the case (see contiguity counts above); the Stage 1 statement is withdrawn.
13. **Single malformed row:** `set_03/train_01/fuzzing-3.csv` contains 1 row whose data_field is 17 hex characters (odd length, > 8 bytes). The audit records counts only, not row positions; its line number is NOT VERIFIED.
14. **Test file with no attack frames:** `set_04/test_04_unknown_vehicle_unknown_attack/force-neutral-2.csv` (17,227,950 B) has attack=1 count 0 despite an attack-family filename.
15. **Stage 1 follow-up (D1):** all 12 files of `set_01/test_04_unknown_vehicle_unknown_attack` are SHA-256-identical to the 12 files of `set_02/test_01_known_vehicle_known_attack` (§B rows 5–16). This confirms at byte level the file identity inferred in Stage 1; the vehicle identity itself remains NOT VERIFIED (no vehicle metadata in files).
16. **Outside the audited folder (observation only, NOT VERIFIED):** a compressed file `C:\dataset\cantrainandtest` (≈1.47 GB, “Compressed (zipped) folder”) was visible in File Explorer next to the dataset folder. It was not opened or audited; it may carry download/version information relevant to Stage 1 item “v1 vs v1.5”.

## A. Per-file manifest

Saved as `DATASET_FILE_MANIFEST_STAGE1B.csv` (same folder). Columns: `set`, `subset`, `partition`, `filename`, `attack_family_token`, `relative_path`, `sha256`, `size_bytes`, `header_raw`, `column_names`, `schema_exact_match`, `has_utf8_bom`, `row_count`, `blank_line_count`, `malformed_row_count`, `malformed_wrong_field_count`, `malformed_bad_timestamp`, `malformed_bad_arbitration_id`, `malformed_bad_data_field`, `malformed_bad_attack_label`, `attack0_count`, `attack1_count`, `attack_ratio`, `empty_data_field_count`, `empty_data_field_attack1_count`, `timestamp_min`, `timestamp_max`, `timestamp_span_s`, `timestamp_decrease_count`, `timestamp_equal_consecutive_count`, `timestamp_max_decrease_s`, `unique_arbitration_id_count`, `arbitration_id_hexlen_min`, `arbitration_id_hexlen_max`, `data_field_hexlen_min`, `data_field_hexlen_max`, `data_field_hexlen_min_nonempty`, `odd_hexlen_data_field_count`, `attack_episode_count`, `attack_contiguity`, `first_attack_row`, `last_attack_row`, `longest_attack_episode_rows`, `attack_row_density_within_span`, `first_attack_timestamp`, `last_attack_timestamp`, `attack_time_span_s`, `max_gap_between_attack_frames_s`, `attack_time_episode_count_gap_gt_1s`, `attack_time_contiguity_gap_gt_1s`, `quoted_row_count`, `file_ends_with_newline`, `error`.

Condensed view:

| set | subset | file | rows | a=1 | ratio | empty df | ts dec | IDs | df len | row eps | time win | SHA-256 (12) |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| set_01 | test_01 | DoS-3.csv | 154,255 | 19,223 | 0.12462 | 0 | 0 | 51 | 4–16 | 8340 | 3 | `f86c0df69c26` |
| set_01 | test_01 | DoS-4.csv | 920,350 | 36,146 | 0.03927 | 0 | 0 | 51 | 4–16 | 15500 | 2 | `c26eb8dea1e5` |
| set_01 | test_01 | force-neutral-3.csv | 904,145 | 2,232 | 0.00247 | 0 | 50 | 51 | 4–16 | 1993 | 1 | `b237c080dbf7` |
| set_01 | test_01 | force-neutral-4.csv | 839,873 | 259 | 0.00031 | 0 | 9 | 51 | 4–16 | 259 | 1 | `5f6bacd0c1e9` |
| set_01 | test_01 | rpm-3.csv | 809,398 | 3,596 | 0.00444 | 0 | 100 | 51 | 4–16 | 3161 | 1 | `21ca5c3341b5` |
| set_01 | test_01 | rpm-4.csv | 824,211 | 325 | 0.00039 | 0 | 8 | 51 | 4–16 | 325 | 1 | `aef3d15f39c6` |
| set_01 | test_01 | standstill-3.csv | 629,156 | 1,447 | 0.00230 | 0 | 59 | 51 | 4–16 | 1447 | 1 | `0d4e08589fc3` |
| set_01 | test_01 | standstill-4.csv | 621,282 | 52 | 0.00008 | 0 | 0 | 51 | 4–16 | 52 | 1 | `ed30a557065d` |
| set_01 | test_02 | DoS-3.csv | 1,100,971 | 157,652 | 0.14319 | 0 | 0 | 98 | 2–16 | 96234 | 1 | `543c7f0f3218` |
| set_01 | test_02 | DoS-4.csv | 689,028 | 5,924 | 0.00860 | 0 | 0 | 98 | 2–16 | 3659 | 1 | `2f059858b0b2` |
| set_01 | test_02 | force-neutral-3.csv | 449,461 | 32 | 0.00007 | 0 | 1 | 98 | 2–16 | 32 | 1 | `be45ea3adc7d` |
| set_01 | test_02 | force-neutral-4.csv | 1,646,238 | 56 | 0.00003 | 0 | 5 | 98 | 2–16 | 56 | 1 | `2b7b9c19741b` |
| set_01 | test_02 | rpm-3.csv | 635,397 | 126 | 0.00020 | 0 | 5 | 98 | 2–16 | 126 | 1 | `03113c53b5eb` |
| set_01 | test_02 | rpm-4.csv | 645,613 | 26 | 0.00004 | 0 | 2 | 98 | 2–16 | 26 | 26 | `f3c5b8f07306` |
| set_01 | test_02 | standstill-3.csv | 635,543 | 272 | 0.00043 | 0 | 10 | 98 | 2–16 | 272 | 1 | `9956ebfa2702` |
| set_01 | test_02 | standstill-4.csv | 645,666 | 79 | 0.00012 | 0 | 3 | 98 | 2–16 | 79 | 1 | `5b5e8f61bc9a` |
| set_01 | test_03 | double-3.csv | 902,805 | 892 | 0.00099 | 0 | 33 | 51 | 4–16 | 729 | 1 | `5424301d48e9` |
| set_01 | test_03 | double-4.csv | 840,014 | 400 | 0.00048 | 0 | 31 | 51 | 4–16 | 347 | 1 | `387c28887c3c` |
| set_01 | test_03 | fuzzing-3.csv | 573,786 | 5,937 | 0.01035 | 385 | 0 | 1946 | 0–16 | 5937 | 1 | `526dbd06fa48` |
| set_01 | test_03 | fuzzing-4.csv | 409,146 | 38 | 0.00009 | 1 | 0 | 89 | 0–16 | 38 | 38 | `8a6a60ba7d4d` |
| set_01 | test_03 | interval-3.csv | 786,935 | 4,292 | 0.00545 | 0 | 0 | 51 | 4–16 | 4292 | 2 | `0bded8086f4f` |
| set_01 | test_03 | interval-4.csv | 884,330 | 126 | 0.00014 | 0 | 0 | 51 | 4–16 | 126 | 1 | `01137c00610f` |
| set_01 | test_03 | speed-3.csv | 631,438 | 3,729 | 0.00591 | 0 | 36 | 51 | 4–16 | 3346 | 1 | `28109daa01df` |
| set_01 | test_03 | speed-4.csv | 622,822 | 1,592 | 0.00256 | 0 | 16 | 51 | 4–16 | 1437 | 1 | `531376570b48` |
| set_01 | test_03 | systematic-3.csv | 783,562 | 919 | 0.00117 | 67 | 0 | 940 | 0–16 | 919 | 1 | `f80791575a69` |
| set_01 | test_03 | systematic-4.csv | 567,973 | 124 | 0.00022 | 17 | 0 | 175 | 0–16 | 124 | 1 | `591bff23af57` |
| set_01 | test_03 | triple-3.csv | 807,996 | 2,194 | 0.00272 | 0 | 50 | 51 | 4–16 | 1514 | 1 | `b579b5021587` |
| set_01 | test_03 | triple-4.csv | 824,468 | 582 | 0.00071 | 0 | 14 | 51 | 4–16 | 378 | 1 | `e4537cb5078f` |
| set_01 | test_04 | double-3.csv | 1,106,909 | 1,276 | 0.00115 | 0 | 15 | 62 | 4–16 | 1045 | 1 | `3d24a7fc708c` |
| set_01 | test_04 | double-4.csv | 1,300,435 | 615 | 0.00047 | 0 | 9 | 62 | 4–16 | 490 | 1 | `9e6248652f95` |
| set_01 | test_04 | fuzzing-3.csv | 495,332 | 6,112 | 0.01234 | 370 | 0 | 1925 | 0–16 | 4326 | 1 | `5e3f3d75efff` |
| set_01 | test_04 | fuzzing-4.csv | 619,269 | 203 | 0.00033 | 10 | 0 | 250 | 0–16 | 203 | 1 | `af823272547f` |
| set_01 | test_04 | interval-3.csv | 891,053 | 107 | 0.00012 | 0 | 0 | 62 | 4–16 | 107 | 1 | `1d15c1d078fe` |
| set_01 | test_04 | interval-4.csv | 857,658 | 26 | 0.00003 | 0 | 0 | 62 | 4–16 | 26 | 1 | `07d8e41c9554` |
| set_01 | test_04 | speed-3.csv | 2,625,443 | 3,141 | 0.00120 | 0 | 45 | 62 | 4–16 | 2933 | 1 | `0925bcd53d76` |
| set_01 | test_04 | speed-4.csv | 1,898,360 | 64 | 0.00003 | 0 | 6 | 62 | 4–16 | 64 | 1 | `122cfd410b0d` |
| set_01 | test_04 | systematic-3.csv | 507,374 | 59 | 0.00012 | 4 | 0 | 121 | 0–16 | 59 | 59 | `bb4af22be82a` |
| set_01 | test_04 | systematic-4.csv | 330,614 | 922 | 0.00279 | 61 | 0 | 585 | 0–16 | 922 | 2 | `0687f61bf1c5` |
| set_01 | test_04 | triple-3.csv | 1,993,660 | 606 | 0.00030 | 0 | 10 | 62 | 4–16 | 427 | 1 | `690d047141c7` |
| set_01 | test_04 | triple-4.csv | 594,448 | 1,113 | 0.00187 | 0 | 22 | 62 | 4–16 | 817 | 1 | `122c3d6aebe4` |
| set_01 | train_0 | accessory-1.csv | 207,704 | 0 | 0.00000 | 0 | 0 | 51 | 4–16 | 0 | 0 | `01fd35561a07` |
| set_01 | train_0 | accessory-2.csv | 226,166 | 0 | 0.00000 | 0 | 0 | 51 | 4–16 | 0 | 0 | `6cab63f1d04a` |
| set_01 | train_0 | attack-free-1.csv | 1,952,833 | 0 | 0.00000 | 0 | 0 | 51 | 4–16 | 0 | 0 | `ac377ea04cfc` |
| set_01 | train_0 | attack-free-2.csv | 1,265,599 | 0 | 0.00000 | 0 | 0 | 51 | 4–16 | 0 | 0 | `a78ed1e6e3c2` |
| set_01 | train_0 | DoS-1.csv | 90,169 | 9,139 | 0.10135 | 0 | 0 | 52 | 4–16 | 4065 | 1 | `70ba91332949` |
| set_01 | train_0 | DoS-2.csv | 311,045 | 25,954 | 0.08344 | 0 | 0 | 51 | 4–16 | 11045 | 1 | `ed28da2b77dc` |
| set_01 | train_0 | force-neutral-1.csv | 715,435 | 6,500 | 0.00909 | 0 | 142 | 51 | 4–16 | 5746 | 1 | `90f42168f452` |
| set_01 | train_0 | force-neutral-2.csv | 998,485 | 492 | 0.00049 | 0 | 25 | 51 | 4–16 | 492 | 1 | `a84b2a1d2ca6` |
| set_01 | train_0 | rpm-1.csv | 841,053 | 3,338 | 0.00397 | 0 | 41 | 51 | 4–16 | 2947 | 1 | `44e6b912666f` |
| set_01 | train_0 | rpm-2.csv | 822,459 | 374 | 0.00045 | 0 | 19 | 51 | 4–16 | 374 | 1 | `6627e889f6bc` |
| set_01 | train_0 | standstill-1.csv | 1,955,048 | 2,215 | 0.00113 | 0 | 25 | 51 | 4–16 | 1904 | 1 | `11a514b6d9a1` |
| set_01 | train_0 | standstill-2.csv | 1,267,144 | 1,545 | 0.00122 | 0 | 24 | 51 | 4–16 | 1348 | 1 | `29629eba4179` |
| set_02 | test_01 | double-3.csv | 1,106,909 | 1,276 | 0.00115 | 0 | 15 | 62 | 4–16 | 1045 | 1 | `3d24a7fc708c` |
| set_02 | test_01 | double-4.csv | 1,300,435 | 615 | 0.00047 | 0 | 9 | 62 | 4–16 | 490 | 1 | `9e6248652f95` |
| set_02 | test_01 | fuzzing-3.csv | 495,332 | 6,112 | 0.01234 | 370 | 0 | 1925 | 0–16 | 4326 | 1 | `5e3f3d75efff` |
| set_02 | test_01 | fuzzing-4.csv | 619,269 | 203 | 0.00033 | 10 | 0 | 250 | 0–16 | 203 | 1 | `af823272547f` |
| set_02 | test_01 | interval-3.csv | 891,053 | 107 | 0.00012 | 0 | 0 | 62 | 4–16 | 107 | 1 | `1d15c1d078fe` |
| set_02 | test_01 | interval-4.csv | 857,658 | 26 | 0.00003 | 0 | 0 | 62 | 4–16 | 26 | 1 | `07d8e41c9554` |
| set_02 | test_01 | speed-3.csv | 2,625,443 | 3,141 | 0.00120 | 0 | 45 | 62 | 4–16 | 2933 | 1 | `0925bcd53d76` |
| set_02 | test_01 | speed-4.csv | 1,898,360 | 64 | 0.00003 | 0 | 6 | 62 | 4–16 | 64 | 1 | `122cfd410b0d` |
| set_02 | test_01 | systematic-3.csv | 507,374 | 59 | 0.00012 | 4 | 0 | 121 | 0–16 | 59 | 59 | `bb4af22be82a` |
| set_02 | test_01 | systematic-4.csv | 330,614 | 922 | 0.00279 | 61 | 0 | 585 | 0–16 | 922 | 2 | `0687f61bf1c5` |
| set_02 | test_01 | triple-3.csv | 1,993,660 | 606 | 0.00030 | 0 | 10 | 62 | 4–16 | 427 | 1 | `690d047141c7` |
| set_02 | test_01 | triple-4.csv | 594,448 | 1,113 | 0.00187 | 0 | 22 | 62 | 4–16 | 817 | 1 | `122c3d6aebe4` |
| set_02 | test_02 | double-3.csv | 699,508 | 2,296 | 0.00328 | 0 | 147 | 54 | 2–16 | 1934 | 1 | `5bd2854735dc` |
| set_02 | test_02 | double-4.csv | 611,726 | 1,356 | 0.00222 | 0 | 30 | 54 | 2–16 | 1101 | 1 | `85b6ead48349` |
| set_02 | test_02 | fuzzing-3.csv | 510,835 | 870 | 0.00170 | 57 | 0 | 759 | 0–16 | 870 | 1 | `29710e21dea0` |
| set_02 | test_02 | fuzzing-4.csv | 629,562 | 1,510 | 0.00240 | 70 | 0 | 1096 | 0–16 | 1029 | 1 | `74841dd3090f` |
| set_02 | test_02 | interval-3.csv | 393,679 | 788 | 0.00200 | 0 | 0 | 54 | 2–16 | 197 | 1 | `b17052b50df3` |
| set_02 | test_02 | interval-4.csv | 907,454 | 250 | 0.00028 | 0 | 0 | 54 | 2–16 | 250 | 1 | `f5065b7a4657` |
| set_02 | test_02 | speed-3.csv | 649,177 | 333 | 0.00051 | 0 | 0 | 54 | 2–16 | 329 | 1 | `19eb55a1177d` |
| set_02 | test_02 | speed-4.csv | 486,777 | 334 | 0.00069 | 0 | 0 | 54 | 2–16 | 323 | 1 | `8bef72a087b4` |
| set_02 | test_02 | systematic-3.csv | 1,012,913 | 9,774 | 0.00965 | 605 | 0 | 2048 | 0–16 | 6467 | 4 | `ae04b96d5632` |
| set_02 | test_02 | systematic-4.csv | 1,235,881 | 2,205 | 0.00178 | 131 | 0 | 2048 | 0–16 | 1577 | 1 | `6e7adccb007a` |
| set_02 | test_02 | triple-3.csv | 697,350 | 138 | 0.00020 | 0 | 5 | 54 | 2–16 | 109 | 1 | `ac6b65bedf27` |
| set_02 | test_02 | triple-4.csv | 610,565 | 195 | 0.00032 | 0 | 8 | 54 | 2–16 | 148 | 1 | `5dd78aff99dc` |
| set_02 | test_03 | DoS-3.csv | 971,181 | 13,599 | 0.01400 | 0 | 31 | 62 | 4–16 | 7677 | 1 | `09515cb41fc0` |
| set_02 | test_03 | DoS-4.csv | 521,593 | 15,093 | 0.02894 | 0 | 0 | 62 | 4–16 | 9033 | 1 | `c62f504818cb` |
| set_02 | test_03 | force-neutral-3.csv | 4,210,018 | 33 | 0.00001 | 0 | 3 | 62 | 4–16 | 33 | 1 | `54fc26671f2a` |
| set_02 | test_03 | force-neutral-4.csv | 2,657,027 | 17 | 0.00001 | 0 | 7 | 62 | 4–16 | 17 | 17 | `94f8b2a16466` |
| set_02 | test_03 | rpm-3.csv | 1,254,259 | 13 | 0.00001 | 0 | 3 | 62 | 4–16 | 13 | 1 | `cc67c73603f5` |
| set_02 | test_03 | rpm-4.csv | 1,052,123 | 17 | 0.00002 | 0 | 3 | 62 | 4–16 | 17 | 1 | `a04c5f5c449d` |
| set_02 | test_03 | standstill-3.csv | 686,802 | 6 | 0.00001 | 0 | 2 | 62 | 4–16 | 6 | 6 | `12c2c412b7ea` |
| set_02 | test_03 | standstill-4.csv | 797,053 | 13 | 0.00002 | 0 | 0 | 62 | 4–16 | 13 | 13 | `f450cbb09f49` |
| set_02 | test_04 | DoS-3.csv | 291,582 | 4,569 | 0.01567 | 0 | 0 | 54 | 2–16 | 2495 | 1 | `85ead308d4be` |
| set_02 | test_04 | DoS-4.csv | 653,469 | 9,830 | 0.01504 | 0 | 0 | 54 | 2–16 | 1186 | 1 | `2058c8be5fca` |
| set_02 | test_04 | force-neutral-3.csv | 479,368 | 1,244 | 0.00260 | 0 | 0 | 54 | 2–16 | 1244 | 4 | `db03d56afd86` |
| set_02 | test_04 | force-neutral-4.csv | 870,399 | 334 | 0.00038 | 0 | 0 | 54 | 2–16 | 287 | 1 | `b8d20162ee2d` |
| set_02 | test_04 | rpm-3.csv | 689,308 | 566 | 0.00082 | 0 | 0 | 54 | 2–16 | 500 | 1 | `3e14a91556ab` |
| set_02 | test_04 | rpm-4.csv | 642,822 | 880 | 0.00137 | 0 | 0 | 54 | 2–16 | 857 | 8 | `d456f171549d` |
| set_02 | test_04 | standstill-3.csv | 810,295 | 513 | 0.00063 | 0 | 0 | 54 | 2–16 | 431 | 1 | `e5413befc968` |
| set_02 | test_04 | standstill-4.csv | 352,661 | 72 | 0.00020 | 0 | 0 | 50 | 2–16 | 72 | 1 | `df9c4d58bad7` |
| set_02 | train_0 | accessory-1.csv | 529,370 | 0 | 0.00000 | 0 | 0 | 62 | 4–16 | 0 | 0 | `62427805f140` |
| set_02 | train_0 | accessory-2.csv | 307,057 | 0 | 0.00000 | 0 | 0 | 62 | 4–16 | 0 | 0 | `e6344c56f303` |
| set_02 | train_0 | attack-free-1.csv | 889,331 | 0 | 0.00000 | 0 | 0 | 62 | 4–16 | 0 | 0 | `67a9f49eaf95` |
| set_02 | train_0 | attack-free-2.csv | 573,956 | 0 | 0.00000 | 0 | 0 | 62 | 4–16 | 0 | 0 | `35439b17fc19` |
| set_02 | train_0 | double-1.csv | 1,092,582 | 4,955 | 0.00454 | 0 | 73 | 62 | 4–16 | 3878 | 1 | `70bb4ce03b30` |
| set_02 | train_0 | double-2.csv | 463,001 | 8,900 | 0.01922 | 0 | 82 | 62 | 4–16 | 6739 | 1 | `9e8b61b1097b` |
| set_02 | train_0 | fuzzing-1.csv | 1,235,992 | 113,514 | 0.09184 | 7165 | 0 | 2048 | 0–16 | 80503 | 1 | `e6d2f8117c1d` |
| set_02 | train_0 | fuzzing-2.csv | 1,167,769 | 6,113 | 0.00523 | 359 | 0 | 1935 | 0–16 | 6113 | 1 | `b9c68d608824` |
| set_02 | train_0 | interval-1.csv | 634,191 | 15,125 | 0.02385 | 0 | 3424 | 62 | 4–16 | 15125 | 1 | `eac9c98a5be6` |
| set_02 | train_0 | interval-2.csv | 1,653,840 | 1,179 | 0.00071 | 0 | 71 | 62 | 4–16 | 1179 | 1 | `f8cc87d7bb86` |
| set_02 | train_0 | speed-1.csv | 2,619,677 | 14 | 0.00001 | 0 | 6 | 62 | 4–16 | 14 | 1 | `0479e4b539c3` |
| set_02 | train_0 | speed-2.csv | 2,734,513 | 38 | 0.00001 | 0 | 6 | 62 | 4–16 | 38 | 1 | `a2f91f422d35` |
| set_02 | train_0 | systematic-1.csv | 541,323 | 37,125 | 0.06858 | 2324 | 0 | 2048 | 0–16 | 26422 | 1 | `d88b9fdef1de` |
| set_02 | train_0 | systematic-2.csv | 456,086 | 2,259 | 0.00495 | 134 | 0 | 2048 | 0–16 | 2259 | 1 | `4cda452db291` |
| set_02 | train_0 | triple-1.csv | 1,780,543 | 31,056 | 0.01744 | 0 | 355 | 62 | 4–16 | 21680 | 1 | `b0416e85aee3` |
| set_02 | train_0 | triple-2.csv | 661,579 | 4,059 | 0.00614 | 0 | 62 | 62 | 4–16 | 2815 | 1 | `c77c613f5b49` |
| set_03 | test_01 | DoS-1.csv | 252,707 | 43,783 | 0.17326 | 0 | 0 | 99 | 2–16 | 27881 | 1 | `613cccc90b4b` |
| set_03 | test_01 | DoS-2.csv | 445,731 | 54,245 | 0.12170 | 0 | 0 | 99 | 2–16 | 32417 | 2 | `bfab0551b580` |
| set_03 | test_01 | double-1.csv | 1,257,705 | 3,073 | 0.00244 | 0 | 60 | 98 | 2–16 | 2577 | 1 | `dff5721a68b7` |
| set_03 | test_01 | double-2.csv | 920,226 | 1,960 | 0.00213 | 0 | 28 | 98 | 2–16 | 1594 | 1 | `6971d4b0a554` |
| set_03 | test_01 | force-neutral-1.csv | 1,257,602 | 2,970 | 0.00236 | 0 | 64 | 98 | 2–16 | 2935 | 2 | `13d169efecfd` |
| set_03 | test_01 | force-neutral-2.csv | 918,980 | 714 | 0.00078 | 0 | 31 | 98 | 2–16 | 714 | 1 | `ddb88c617ab4` |
| set_03 | test_01 | fuzzing-1.csv | 1,059,035 | 50,522 | 0.04771 | 3143 | 0 | 2048 | 0–16 | 42031 | 1 | `f34e37786f1f` |
| set_03 | test_01 | fuzzing-2.csv | 793,574 | 553 | 0.00070 | 27 | 0 | 563 | 0–16 | 553 | 5 | `b1a796dab1f0` |
| set_03 | test_01 | triple-1.csv | 524,898 | 2,210 | 0.00421 | 0 | 28 | 98 | 2–16 | 1638 | 1 | `3482481b495c` |
| set_03 | test_01 | triple-2.csv | 1,145,333 | 2,475 | 0.00216 | 0 | 38 | 98 | 2–16 | 1884 | 1 | `45d7e923c304` |
| set_03 | test_02 | DoS-1.csv | 643,807 | 12,091 | 0.01878 | 0 | 0 | 55 | 2–16 | 6641 | 1 | `ba70baaa2e7e` |
| set_03 | test_02 | DoS-2.csv | 709,039 | 25,308 | 0.03569 | 0 | 0 | 54 | 2–16 | 14005 | 6 | `8ac793414409` |
| set_03 | test_02 | double-1.csv | 1,244,063 | 10,387 | 0.00835 | 0 | 197 | 54 | 2–16 | 8020 | 3 | `cb6e794a3de5` |
| set_03 | test_02 | double-2.csv | 695,540 | 4,614 | 0.00663 | 0 | 87 | 54 | 2–16 | 3388 | 1 | `c592898c200f` |
| set_03 | test_02 | force-neutral-1.csv | 527,589 | 1,720 | 0.00326 | 0 | 0 | 54 | 2–16 | 1720 | 1 | `c1a10149201f` |
| set_03 | test_02 | force-neutral-2.csv | 475,757 | 1,379 | 0.00290 | 0 | 0 | 54 | 2–16 | 1117 | 1 | `c24ae73768ef` |
| set_03 | test_02 | fuzzing-1.csv | 660,170 | 28,454 | 0.04310 | 1837 | 0 | 2048 | 0–16 | 18559 | 3 | `4d3db9215b3a` |
| set_03 | test_02 | fuzzing-2.csv | 650,196 | 6,557 | 0.01008 | 434 | 0 | 1961 | 0–16 | 5184 | 2 | `00c41be1a38f` |
| set_03 | test_02 | triple-1.csv | 544,385 | 52,917 | 0.09721 | 0 | 821 | 54 | 2–16 | 35612 | 1 | `a20dca9b3342` |
| set_03 | test_02 | triple-2.csv | 703,688 | 12,762 | 0.01814 | 0 | 202 | 54 | 2–16 | 8721 | 3 | `3d46aaada8ed` |
| set_03 | test_03 | interval-1.csv | 950,657 | 7,338 | 0.00772 | 0 | 0 | 98 | 2–16 | 3669 | 1 | `42499589968f` |
| set_03 | test_03 | interval-2.csv | 1,009,145 | 632 | 0.00063 | 0 | 0 | 98 | 2–16 | 316 | 6 | `6cfbccd88380` |
| set_03 | test_03 | rpm-1.csv | 524,212 | 1,524 | 0.00291 | 0 | 32 | 98 | 2–16 | 1503 | 1 | `61b3cf335539` |
| set_03 | test_03 | rpm-2.csv | 1,143,081 | 223 | 0.00020 | 0 | 20 | 98 | 2–16 | 223 | 1 | `c6c9d0508c4b` |
| set_03 | test_03 | rpm-accessory-1.csv | 166,162 | 28 | 0.00017 | 0 | 1 | 98 | 2–16 | 28 | 28 | `981dabcbffb3` |
| set_03 | test_03 | rpm-accessory-2.csv | 149,740 | 30 | 0.00020 | 0 | 1 | 98 | 2–16 | 30 | 30 | `c1e3b545cb3f` |
| set_03 | test_03 | speed-1.csv | 1,255,235 | 603 | 0.00048 | 0 | 12 | 98 | 2–16 | 603 | 1 | `9e8896f38614` |
| set_03 | test_03 | speed-2.csv | 919,087 | 821 | 0.00089 | 0 | 19 | 98 | 2–16 | 821 | 1 | `8490cacc2881` |
| set_03 | test_03 | speed-accessory-1.csv | 170,115 | 3,981 | 0.02340 | 0 | 55 | 98 | 2–16 | 3868 | 1 | `9179c3769ac8` |
| set_03 | test_03 | speed-accessory-2.csv | 149,831 | 121 | 0.00081 | 0 | 5 | 98 | 2–16 | 121 | 1 | `9a5cea5a4134` |
| set_03 | test_03 | standstill-1.csv | 524,245 | 1,557 | 0.00297 | 0 | 36 | 98 | 2–16 | 1535 | 1 | `31aea31368aa` |
| set_03 | test_03 | standstill-2.csv | 1,143,404 | 546 | 0.00048 | 0 | 14 | 98 | 2–16 | 546 | 1 | `013908f69690` |
| set_03 | test_03 | systematic-1.csv | 776,168 | 496 | 0.00064 | 30 | 0 | 548 | 0–16 | 496 | 1 | `eaf6b5a45b6a` |
| set_03 | test_03 | systematic-2.csv | 566,869 | 252 | 0.00044 | 12 | 0 | 339 | 0–16 | 252 | 1 | `c32557dff2d7` |
| set_03 | test_04 | interval-1.csv | 857,154 | 91,684 | 0.10696 | 0 | 0 | 54 | 2–16 | 22918 | 1 | `bae034158b49` |
| set_03 | test_04 | interval-2.csv | 465,145 | 13,592 | 0.02922 | 0 | 0 | 54 | 2–16 | 13591 | 1 | `4c0d7fd5fabc` |
| set_03 | test_04 | rpm-1.csv | 488,528 | 4,830 | 0.00989 | 0 | 0 | 54 | 2–16 | 4575 | 5 | `ed1de9001aad` |
| set_03 | test_04 | rpm-2.csv | 569,888 | 468 | 0.00082 | 0 | 0 | 54 | 2–16 | 468 | 1 | `8d69e9a2f72d` |
| set_03 | test_04 | rpm-accessory-1.csv | 129,817 | 1,348 | 0.01038 | 0 | 0 | 54 | 2–16 | 1344 | 1 | `0b2cd22e6efa` |
| set_03 | test_04 | rpm-accessory-2.csv | 138,381 | 215 | 0.00155 | 0 | 0 | 50 | 2–16 | 215 | 1 | `f7ff3cd29979` |
| set_03 | test_04 | speed-1.csv | 757,055 | 12,875 | 0.01701 | 0 | 0 | 54 | 2–16 | 12236 | 6 | `7b9b7973e083` |
| set_03 | test_04 | speed-2.csv | 714,871 | 1,358 | 0.00190 | 0 | 0 | 54 | 2–16 | 1276 | 5 | `34dc42612af9` |
| set_03 | test_04 | speed-accessory-1.csv | 262,041 | 1,430 | 0.00546 | 0 | 0 | 50 | 2–16 | 1430 | 1 | `ff264d1b07da` |
| set_03 | test_04 | speed-accessory-2.csv | 164,771 | 90 | 0.00055 | 0 | 0 | 54 | 2–16 | 80 | 1 | `55b79b9c9493` |
| set_03 | test_04 | standstill-1.csv | 306,189 | 7,862 | 0.02568 | 0 | 0 | 50 | 2–16 | 6872 | 1 | `15926e6cb364` |
| set_03 | test_04 | standstill-2.csv | 892,327 | 2,361 | 0.00265 | 0 | 0 | 54 | 2–16 | 2331 | 1 | `7dbd5df9d928` |
| set_03 | test_04 | systematic-1.csv | 519,433 | 9,468 | 0.01823 | 567 | 0 | 2048 | 0–16 | 6448 | 1 | `fe44285f29d4` |
| set_03 | test_04 | systematic-2.csv | 630,419 | 2,367 | 0.00375 | 159 | 0 | 2048 | 0–16 | 2367 | 1 | `7f1cdfd5af58` |
| set_03 | train_0 | accessory-3.csv | 216,573 | 0 | 0.00000 | 0 | 0 | 98 | 2–16 | 0 | 0 | `a852a97e77dd` |
| set_03 | train_0 | accessory-4.csv | 446,433 | 0 | 0.00000 | 0 | 0 | 98 | 2–16 | 0 | 0 | `6d5e8e63931a` |
| set_03 | train_0 | attack-free-3.csv | 1,711,471 | 0 | 0.00000 | 0 | 0 | 98 | 2–16 | 0 | 0 | `058cdaf94c7c` |
| set_03 | train_0 | attack-free-4.csv | 1,295,306 | 0 | 0.00000 | 0 | 0 | 98 | 2–16 | 0 | 0 | `e233edf7aee6` |
| set_03 | train_0 | DoS-3.csv | 1,100,971 | 157,652 | 0.14319 | 0 | 0 | 98 | 2–16 | 96234 | 1 | `543c7f0f3218` |
| set_03 | train_0 | DoS-4.csv | 689,028 | 5,924 | 0.00860 | 0 | 0 | 98 | 2–16 | 3659 | 1 | `2f059858b0b2` |
| set_03 | train_0 | double-3.csv | 449,725 | 296 | 0.00066 | 0 | 7 | 98 | 2–16 | 247 | 1 | `4fe234bb6464` |
| set_03 | train_0 | double-4.csv | 1,646,538 | 356 | 0.00022 | 0 | 4 | 98 | 2–16 | 287 | 1 | `bdfd582e641e` |
| set_03 | train_0 | force-neutral-3.csv | 449,461 | 32 | 0.00007 | 0 | 1 | 98 | 2–16 | 32 | 1 | `be45ea3adc7d` |
| set_03 | train_0 | force-neutral-4.csv | 1,646,238 | 56 | 0.00003 | 0 | 5 | 98 | 2–16 | 56 | 1 | `2b7b9c19741b` |
| set_03 | train_0 | fuzzing-3.csv | 296,365 | 3,848 | 0.01298 | 237 | 0 | 1756 | 0–17 | 3077 | 2 | `7859e3853423` |
| set_03 | train_0 | fuzzing-4.csv | 795,457 | 172 | 0.00022 | 12 | 0 | 257 | 0–16 | 172 | 1 | `e14949c9bfd3` |
| set_03 | train_0 | triple-3.csv | 635,673 | 402 | 0.00063 | 0 | 10 | 98 | 2–16 | 312 | 1 | `b3aa7b898e4c` |
| set_03 | train_0 | triple-4.csv | 646,528 | 941 | 0.00146 | 0 | 14 | 98 | 2–16 | 736 | 1 | `178654eb870c` |
| set_04 | test_01 | interval-1.csv | 857,154 | 91,684 | 0.10696 | 0 | 0 | 54 | 2–16 | 22918 | 1 | `bae034158b49` |
| set_04 | test_01 | interval-2.csv | 465,145 | 13,592 | 0.02922 | 0 | 0 | 54 | 2–16 | 13591 | 1 | `4c0d7fd5fabc` |
| set_04 | test_01 | rpm-1.csv | 488,528 | 4,830 | 0.00989 | 0 | 0 | 54 | 2–16 | 4575 | 5 | `ed1de9001aad` |
| set_04 | test_01 | rpm-2.csv | 569,888 | 468 | 0.00082 | 0 | 0 | 54 | 2–16 | 468 | 1 | `8d69e9a2f72d` |
| set_04 | test_01 | rpm-accessory-1.csv | 129,817 | 1,348 | 0.01038 | 0 | 0 | 54 | 2–16 | 1344 | 1 | `0b2cd22e6efa` |
| set_04 | test_01 | rpm-accessory-2.csv | 138,381 | 215 | 0.00155 | 0 | 0 | 50 | 2–16 | 215 | 1 | `f7ff3cd29979` |
| set_04 | test_01 | speed-1.csv | 757,055 | 12,875 | 0.01701 | 0 | 0 | 54 | 2–16 | 12236 | 6 | `7b9b7973e083` |
| set_04 | test_01 | speed-2.csv | 714,871 | 1,358 | 0.00190 | 0 | 0 | 54 | 2–16 | 1276 | 5 | `34dc42612af9` |
| set_04 | test_01 | speed-accessory-1.csv | 262,041 | 1,430 | 0.00546 | 0 | 0 | 50 | 2–16 | 1430 | 1 | `ff264d1b07da` |
| set_04 | test_01 | speed-accessory-2.csv | 164,771 | 90 | 0.00055 | 0 | 0 | 54 | 2–16 | 80 | 1 | `55b79b9c9493` |
| set_04 | test_01 | standstill-1.csv | 306,189 | 7,862 | 0.02568 | 0 | 0 | 50 | 2–16 | 6872 | 1 | `15926e6cb364` |
| set_04 | test_01 | standstill-2.csv | 892,327 | 2,361 | 0.00265 | 0 | 0 | 54 | 2–16 | 2331 | 1 | `7dbd5df9d928` |
| set_04 | test_01 | systematic-1.csv | 519,433 | 9,468 | 0.01823 | 567 | 0 | 2048 | 0–16 | 6448 | 1 | `fe44285f29d4` |
| set_04 | test_01 | systematic-2.csv | 630,419 | 2,367 | 0.00375 | 159 | 0 | 2048 | 0–16 | 2367 | 1 | `7f1cdfd5af58` |
| set_04 | test_02 | interval-1.csv | 634,191 | 15,125 | 0.02385 | 0 | 3424 | 62 | 4–16 | 15125 | 1 | `eac9c98a5be6` |
| set_04 | test_02 | interval-2.csv | 1,653,840 | 1,179 | 0.00071 | 0 | 71 | 62 | 4–16 | 1179 | 1 | `f8cc87d7bb86` |
| set_04 | test_02 | rpm-1.csv | 3,296,008 | 411 | 0.00012 | 0 | 19 | 62 | 4–16 | 411 | 1 | `adccfc1418c2` |
| set_04 | test_02 | rpm-2.csv | 1,975,925 | 94 | 0.00005 | 0 | 5 | 62 | 4–16 | 94 | 1 | `060d1a2c3407` |
| set_04 | test_02 | rpm-accessory-1.csv | 529,658 | 288 | 0.00054 | 0 | 10 | 62 | 4–16 | 288 | 1 | `9739daaa2b61` |
| set_04 | test_02 | rpm-accessory-2.csv | 307,113 | 56 | 0.00018 | 0 | 2 | 62 | 4–16 | 56 | 2 | `ab71eeac381c` |
| set_04 | test_02 | speed-1.csv | 2,619,677 | 14 | 0.00001 | 0 | 6 | 62 | 4–16 | 14 | 1 | `0479e4b539c3` |
| set_04 | test_02 | speed-2.csv | 2,734,513 | 38 | 0.00001 | 0 | 6 | 62 | 4–16 | 38 | 1 | `a2f91f422d35` |
| set_04 | test_02 | speed-accessory-1.csv | 529,420 | 50 | 0.00009 | 0 | 2 | 62 | 4–16 | 50 | 1 | `4a6fea5f7181` |
| set_04 | test_02 | speed-accessory-2.csv | 307,067 | 10 | 0.00003 | 0 | 0 | 62 | 4–16 | 10 | 10 | `7f7ada628691` |
| set_04 | test_02 | standstill-1.csv | 1,208,289 | 566 | 0.00047 | 0 | 18 | 62 | 4–16 | 566 | 2 | `46cd4879e286` |
| set_04 | test_02 | standstill-2.csv | 614,984 | 24 | 0.00004 | 0 | 2 | 62 | 4–16 | 24 | 24 | `fbbe59b02dd7` |
| set_04 | test_02 | systematic-1.csv | 541,323 | 37,125 | 0.06858 | 2324 | 0 | 2048 | 0–16 | 26422 | 1 | `d88b9fdef1de` |
| set_04 | test_02 | systematic-2.csv | 456,086 | 2,259 | 0.00495 | 134 | 0 | 2048 | 0–16 | 2259 | 1 | `4cda452db291` |
| set_04 | test_03 | DoS-1.csv | 643,807 | 12,091 | 0.01878 | 0 | 0 | 55 | 2–16 | 6641 | 1 | `ba70baaa2e7e` |
| set_04 | test_03 | DoS-2.csv | 709,039 | 25,308 | 0.03569 | 0 | 0 | 54 | 2–16 | 14005 | 6 | `8ac793414409` |
| set_04 | test_03 | double-1.csv | 1,244,063 | 10,387 | 0.00835 | 0 | 197 | 54 | 2–16 | 8020 | 3 | `cb6e794a3de5` |
| set_04 | test_03 | double-2.csv | 695,540 | 4,614 | 0.00663 | 0 | 87 | 54 | 2–16 | 3388 | 1 | `c592898c200f` |
| set_04 | test_03 | force-neutral-1.csv | 527,589 | 1,720 | 0.00326 | 0 | 0 | 54 | 2–16 | 1720 | 1 | `c1a10149201f` |
| set_04 | test_03 | force-neutral-2.csv | 475,757 | 1,379 | 0.00290 | 0 | 0 | 54 | 2–16 | 1117 | 1 | `c24ae73768ef` |
| set_04 | test_03 | fuzzing-1.csv | 660,170 | 28,454 | 0.04310 | 1837 | 0 | 2048 | 0–16 | 18559 | 3 | `4d3db9215b3a` |
| set_04 | test_03 | fuzzing-2.csv | 650,196 | 6,557 | 0.01008 | 434 | 0 | 1961 | 0–16 | 5184 | 2 | `00c41be1a38f` |
| set_04 | test_03 | triple-1.csv | 544,385 | 52,917 | 0.09721 | 0 | 821 | 54 | 2–16 | 35612 | 1 | `a20dca9b3342` |
| set_04 | test_03 | triple-2.csv | 703,688 | 12,762 | 0.01814 | 0 | 202 | 54 | 2–16 | 8721 | 3 | `3d46aaada8ed` |
| set_04 | test_04 | DoS-1.csv | 402,001 | 20,560 | 0.05114 | 0 | 0 | 63 | 4–16 | 12260 | 1 | `c254937a2996` |
| set_04 | test_04 | DoS-2.csv | 416,866 | 30,648 | 0.07352 | 0 | 0 | 62 | 4–16 | 17528 | 1 | `2b6dafa512e4` |
| set_04 | test_04 | double-1.csv | 1,092,582 | 4,955 | 0.00454 | 0 | 73 | 62 | 4–16 | 3878 | 1 | `70bb4ce03b30` |
| set_04 | test_04 | double-2.csv | 463,001 | 8,900 | 0.01922 | 0 | 82 | 62 | 4–16 | 6739 | 1 | `9e8b61b1097b` |
| set_04 | test_04 | force-neutral-1.csv | 509,087 | 1,166 | 0.00229 | 0 | 19 | 62 | 4–16 | 1166 | 1 | `86679f0754d9` |
| set_04 | test_04 | force-neutral-2.csv | 454,206 | 0 | 0.00000 | 0 | 0 | 62 | 4–16 | 0 | 0 | `0a4fe4972cbd` |
| set_04 | test_04 | fuzzing-1.csv | 1,235,992 | 113,514 | 0.09184 | 7165 | 0 | 2048 | 0–16 | 80503 | 1 | `e6d2f8117c1d` |
| set_04 | test_04 | fuzzing-2.csv | 1,167,769 | 6,113 | 0.00523 | 359 | 0 | 1935 | 0–16 | 6113 | 1 | `b9c68d608824` |
| set_04 | test_04 | triple-1.csv | 1,780,543 | 31,056 | 0.01744 | 0 | 355 | 62 | 4–16 | 21680 | 1 | `b0416e85aee3` |
| set_04 | test_04 | triple-2.csv | 661,579 | 4,059 | 0.00614 | 0 | 62 | 62 | 4–16 | 2815 | 1 | `c77c613f5b49` |
| set_04 | train_0 | accessory-3.csv | 31,991 | 0 | 0.00000 | 0 | 0 | 13 | 2–16 | 0 | 0 | `34c1d08661f0` |
| set_04 | train_0 | accessory-4.csv | 52,783 | 0 | 0.00000 | 0 | 0 | 48 | 2–16 | 0 | 0 | `4d7d5102dcb6` |
| set_04 | train_0 | attack-free-3.csv | 920,346 | 0 | 0.00000 | 0 | 0 | 54 | 2–16 | 0 | 0 | `97ada5df687c` |
| set_04 | train_0 | attack-free-4.csv | 336,011 | 0 | 0.00000 | 0 | 0 | 54 | 2–16 | 0 | 0 | `1e8a717287a4` |
| set_04 | train_0 | interval-3.csv | 393,679 | 788 | 0.00200 | 0 | 0 | 54 | 2–16 | 197 | 1 | `b17052b50df3` |
| set_04 | train_0 | interval-4.csv | 907,454 | 250 | 0.00028 | 0 | 0 | 54 | 2–16 | 250 | 1 | `f5065b7a4657` |
| set_04 | train_0 | rpm-3.csv | 689,308 | 566 | 0.00082 | 0 | 0 | 54 | 2–16 | 500 | 1 | `3e14a91556ab` |
| set_04 | train_0 | rpm-4.csv | 642,822 | 880 | 0.00137 | 0 | 0 | 54 | 2–16 | 857 | 8 | `d456f171549d` |
| set_04 | train_0 | rpm-accessory-3.csv | 157,883 | 229 | 0.00145 | 0 | 0 | 50 | 2–16 | 221 | 1 | `1a59a410adf0` |
| set_04 | train_0 | rpm-accessory-4.csv | 175,015 | 8,293 | 0.04738 | 0 | 0 | 54 | 2–16 | 6502 | 1 | `0e24c2bba904` |
| set_04 | train_0 | speed-3.csv | 649,177 | 333 | 0.00051 | 0 | 0 | 54 | 2–16 | 329 | 1 | `19eb55a1177d` |
| set_04 | train_0 | speed-4.csv | 486,777 | 334 | 0.00069 | 0 | 0 | 54 | 2–16 | 323 | 1 | `8bef72a087b4` |
| set_04 | train_0 | speed-accessory-3.csv | 249,865 | 205 | 0.00082 | 0 | 0 | 50 | 2–16 | 146 | 1 | `a6db376f872b` |
| set_04 | train_0 | speed-accessory-4.csv | 387,940 | 1,637 | 0.00422 | 0 | 32 | 54 | 2–16 | 1571 | 1 | `0b0f03254871` |
| set_04 | train_0 | standstill-3.csv | 810,295 | 513 | 0.00063 | 0 | 0 | 54 | 2–16 | 431 | 1 | `e5413befc968` |
| set_04 | train_0 | standstill-4.csv | 352,661 | 72 | 0.00020 | 0 | 0 | 50 | 2–16 | 72 | 1 | `df9c4d58bad7` |
| set_04 | train_0 | systematic-3.csv | 1,012,913 | 9,774 | 0.00965 | 605 | 0 | 2048 | 0–16 | 6467 | 4 | `ae04b96d5632` |
| set_04 | train_0 | systematic-4.csv | 1,235,881 | 2,205 | 0.00178 | 131 | 0 | 2048 | 0–16 | 1577 | 1 | `6e7adccb007a` |
