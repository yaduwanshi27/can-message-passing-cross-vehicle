#!/usr/bin/env python3
"""
STAGE 1B — read-only integrity audit of can-train-and-test.
Standard library only. Streams every CSV from disk; never modifies, copies or samples data.

Usage:  python audit_stage1b.py [DATASET_ROOT] [OUTPUT_DIR]
Default DATASET_ROOT = C:\\dataset\\can-train-and-test
Outputs (in OUTPUT_DIR, default = DATASET_ROOT\\_stage1b_outputs):
  DATASET_FILE_MANIFEST_STAGE1B.csv   one row per CSV
  STAGE1B_RUNLOG.txt                  environment + timings
"""
import csv, hashlib, os, re, sys, time, platform, json
from multiprocessing import Pool, cpu_count

EXPECTED = ["timestamp", "arbitration_id", "data_field", "attack"]
HEX = re.compile(r"^[0-9A-Fa-f]+$")
CHUNK = 8 * 1024 * 1024
GAP_S = 1.0  # fixed, pre-declared threshold for time-level attack episodes

FIELDS = [
    "set", "subset", "partition", "filename", "attack_family_token", "relative_path",
    "sha256", "size_bytes",
    "header_raw", "column_names", "schema_exact_match", "has_utf8_bom",
    "row_count", "blank_line_count",
    "malformed_row_count", "malformed_wrong_field_count", "malformed_bad_timestamp",
    "malformed_bad_arbitration_id", "malformed_bad_data_field", "malformed_bad_attack_label",
    "attack0_count", "attack1_count", "attack_ratio",
    "empty_data_field_count", "empty_data_field_attack1_count",
    "timestamp_min", "timestamp_max", "timestamp_span_s",
    "timestamp_decrease_count", "timestamp_equal_consecutive_count", "timestamp_max_decrease_s",
    "unique_arbitration_id_count", "arbitration_id_hexlen_min", "arbitration_id_hexlen_max",
    "data_field_hexlen_min", "data_field_hexlen_max", "data_field_hexlen_min_nonempty",
    "odd_hexlen_data_field_count",
    "attack_episode_count", "attack_contiguity", "first_attack_row", "last_attack_row",
    "longest_attack_episode_rows", "attack_row_density_within_span",
    "first_attack_timestamp", "last_attack_timestamp", "attack_time_span_s",
    "max_gap_between_attack_frames_s", "attack_time_episode_count_gap_gt_1s", "attack_time_contiguity_gap_gt_1s",
    "file_ends_with_newline",
    "error",
]


def family_token(fn):
    return re.sub(r"-\d+\.csv$", "", fn)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ends_with_newline(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        if f.tell() == 0:
            return False
        f.seek(-1, 2)
        return f.read(1) in (b"\n", b"\r")


def audit(args):
    root, rel = args
    parts = rel.replace("\\", "/").split("/")
    st, sub, fn = parts[0], parts[1], parts[2]
    path = os.path.join(root, *parts)
    r = {k: "" for k in FIELDS}
    r.update({"set": st, "subset": sub, "partition": "train" if sub.startswith("train") else "test",
              "filename": fn, "attack_family_token": family_token(fn), "relative_path": "/".join(parts)})
    try:
        r["size_bytes"] = os.path.getsize(path)
        r["sha256"] = sha256_file(path)
        r["file_ends_with_newline"] = ends_with_newline(path)

        rows = blank = 0
        m_fields = m_ts = m_id = m_df = m_lab = malformed = 0
        a0 = a1 = empty = empty_a1 = 0
        tmin = float("inf"); tmax = float("-inf")
        dec = eq = 0; maxdec = 0.0
        prev_ts = None
        ids = set(); idl_min = 10**9; idl_max = -1
        dl_min = 10**9; dl_max = -1; dl_min_ne = 10**9; odd = 0
        episodes = 0; in_ep = False; first_a = last_a = None; cur_len = 0; longest = 0
        first_ats = last_ats = None; max_agap = 0.0; tgaps = 0

        with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
            r["has_utf8_bom"] = first_line.startswith("\ufeff")
            header_raw = first_line.rstrip("\r\n")
            r["header_raw"] = header_raw
            cols = next(csv.reader([header_raw.lstrip("\ufeff")]))
            r["column_names"] = "|".join(cols)
            r["schema_exact_match"] = (cols == EXPECTED) and not r["has_utf8_bom"]
            reader = csv.reader(f)
            idx = -1
            for row in reader:
                if not row:
                    blank += 1
                    continue
                idx += 1
                rows += 1
                bad = False
                if len(row) != 4:
                    m_fields += 1
                    malformed += 1
                    # attack-episode tracking treats malformed rows as non-attack
                    if in_ep:
                        in_ep = False; longest = max(longest, cur_len)
                    continue
                ts_s, aid, df, lab = row
                # timestamp
                try:
                    ts = float(ts_s)
                    if ts != ts:
                        raise ValueError
                except ValueError:
                    ts = None; m_ts += 1; bad = True
                if ts is not None:
                    if ts < tmin: tmin = ts
                    if ts > tmax: tmax = ts
                    if prev_ts is not None:
                        if ts < prev_ts:
                            dec += 1
                            if prev_ts - ts > maxdec: maxdec = prev_ts - ts
                        elif ts == prev_ts:
                            eq += 1
                    prev_ts = ts
                # arbitration id
                if aid and HEX.match(aid) and len(aid) <= 8:
                    ids.add(aid)
                    la = len(aid)
                    if la < idl_min: idl_min = la
                    if la > idl_max: idl_max = la
                else:
                    m_id += 1; bad = True
                # data field
                ld = len(df)
                if ld == 0:
                    empty += 1
                else:
                    if not HEX.match(df) or ld > 16:
                        m_df += 1; bad = True
                    if ld % 2:
                        odd += 1
                    if ld < dl_min_ne: dl_min_ne = ld
                if ld < dl_min: dl_min = ld
                if ld > dl_max: dl_max = ld
                # label
                if lab == "1":
                    a1 += 1
                    if ld == 0: empty_a1 += 1
                    if not in_ep:
                        in_ep = True; episodes += 1; cur_len = 0
                    cur_len += 1
                    if first_a is None: first_a = idx
                    last_a = idx
                    if ts is not None:
                        if first_ats is None:
                            first_ats = ts
                        else:
                            g = ts - last_ats
                            if g > max_agap: max_agap = g
                            if g > GAP_S: tgaps += 1
                        last_ats = ts
                else:
                    if lab == "0":
                        a0 += 1
                    else:
                        m_lab += 1; bad = True
                    if in_ep:
                        in_ep = False; longest = max(longest, cur_len)
                if bad:
                    malformed += 1
            if in_ep:
                longest = max(longest, cur_len)

        r.update({
            "row_count": rows, "blank_line_count": blank,
            "malformed_row_count": malformed, "malformed_wrong_field_count": m_fields,
            "malformed_bad_timestamp": m_ts, "malformed_bad_arbitration_id": m_id,
            "malformed_bad_data_field": m_df, "malformed_bad_attack_label": m_lab,
            "attack0_count": a0, "attack1_count": a1,
            "attack_ratio": f"{a1 / rows:.8f}" if rows else "",
            "empty_data_field_count": empty, "empty_data_field_attack1_count": empty_a1,
            "timestamp_min": repr(tmin) if rows else "", "timestamp_max": repr(tmax) if rows else "",
            "timestamp_span_s": f"{tmax - tmin:.6f}" if rows else "",
            "timestamp_decrease_count": dec, "timestamp_equal_consecutive_count": eq,
            "timestamp_max_decrease_s": f"{maxdec:.9f}",
            "unique_arbitration_id_count": len(ids),
            "arbitration_id_hexlen_min": idl_min if idl_max >= 0 else "",
            "arbitration_id_hexlen_max": idl_max if idl_max >= 0 else "",
            "data_field_hexlen_min": dl_min if dl_max >= 0 else "",
            "data_field_hexlen_max": dl_max if dl_max >= 0 else "",
            "data_field_hexlen_min_nonempty": dl_min_ne if dl_min_ne < 10**9 else "",
            "odd_hexlen_data_field_count": odd,
            "attack_episode_count": episodes,
            "attack_contiguity": ("none" if episodes == 0 else "single_contiguous" if episodes == 1 else "multiple"),
            "first_attack_row": "" if first_a is None else first_a,
            "last_attack_row": "" if last_a is None else last_a,
            "longest_attack_episode_rows": longest,
            "attack_row_density_within_span": (f"{a1 / (last_a - first_a + 1):.6f}" if first_a is not None else ""),
            "first_attack_timestamp": "" if first_ats is None else repr(first_ats),
            "last_attack_timestamp": "" if last_ats is None else repr(last_ats),
            "attack_time_span_s": "" if first_ats is None else f"{last_ats - first_ats:.6f}",
            "max_gap_between_attack_frames_s": "" if first_ats is None else f"{max_agap:.6f}",
            "attack_time_episode_count_gap_gt_1s": 0 if first_ats is None else tgaps + 1,
            "attack_time_contiguity_gap_gt_1s": ("none" if first_ats is None else "single_window" if tgaps == 0 else "multiple_windows"),
        })
    except Exception as e:  # record, never abort the whole run
        r["error"] = f"{type(e).__name__}: {e}"
    return r


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"C:\dataset\can-train-and-test"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "_stage1b_outputs")
    os.makedirs(out, exist_ok=True)
    rels = []
    for st in sorted(os.listdir(root)):
        p = os.path.join(root, st)
        if not (os.path.isdir(p) and re.match(r"^set_\d+$", st)):
            continue
        for sub in sorted(os.listdir(p)):
            q = os.path.join(p, sub)
            if not os.path.isdir(q):
                continue
            for fn in sorted(os.listdir(q), key=str.lower):
                if fn.lower().endswith(".csv") and os.path.isfile(os.path.join(q, fn)):
                    rels.append(f"{st}/{sub}/{fn}")
    t0 = time.time()
    print(f"Found {len(rels)} CSV files under {root}", flush=True)
    workers = max(1, min(4, cpu_count()))
    results = []
    with Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(audit, [(root, x) for x in rels]), 1):
            results.append(r)
            print(f"[{i:3d}/{len(rels)}] {r['relative_path']}  rows={r['row_count']}  "
                  f"{'ERROR ' + r['error'] if r['error'] else ''}", flush=True)
    results.sort(key=lambda r: r["relative_path"].lower())
    mpath = os.path.join(out, "DATASET_FILE_MANIFEST_STAGE1B.csv")
    with open(mpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(results)
    with open(os.path.join(out, "STAGE1B_RUNLOG.txt"), "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "script": "audit_stage1b.py", "python": sys.version, "platform": platform.platform(),
            "root": root, "csv_files_found": len(rels), "workers": workers,
            "elapsed_s": round(time.time() - t0, 1),
            "errors": sum(1 for r in results if r["error"]),
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=2))
    print(f"DONE in {time.time() - t0:.0f}s -> {mpath}", flush=True)


if __name__ == "__main__":
    main()
