"""Stage 5b statistics (STAGE2_DESIGN_FROZEN_v1.0 §9 + v1.1 C1). Reads eval scores + frozen thresholds only. CPU/numpy (optional torch GPU, self-checked).
Usage: python exp_stats.py --eval /kaggle/working/eval --out /kaggle/working/stats"""
import os, sys, json, glob, math, argparse, time
import numpy as np
from sklearn.metrics import average_precision_score

MODELS = ['Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired']
ROLE = {'test_01': 'A', 'test_02': 'B', 'test_03': 'C', 'test_04': 'D'}
CONTRASTS = {'H1': ('GraphSAGE', 'DeepSets'), 'H1a': ('GraphSAGE', 'GraphSAGE_rewired'), 'H2': ('GraphSAGE', 'GRU'), 'H3': ('GraphSAGE', 'LightGBM_S'),
             'ladder_LGBS_minus_LGB': ('LightGBM_S', 'LightGBM')}
SECONDARY = ['H1a', 'H2', 'H3']
DEV = None
MARGIN = 0.02; NBOOT = 2000; BOOT_SEED = 20260917; CHUNK = 50

def weighted_ap_prep(s, y, fid, nfiles):
    """Precompute per-file cumulative positive/negative counts at the end of each tied-score group (sklearn tie handling)."""
    o = np.argsort(-s, kind='stable'); ss = s[o]; ys = y[o].astype(np.float64); fs = fid[o]
    ends = np.r_[np.flatnonzero(ss[1:] != ss[:-1]), len(ss) - 1]
    CP = np.zeros((nfiles, len(ends))); CN = np.zeros((nfiles, len(ends)))
    for f in range(nfiles):
        m = fs == f
        CP[f] = np.cumsum(m * ys)[ends]; CN[f] = np.cumsum(m * (1 - ys))[ends]
    return CP, CN

def weighted_ap(CP, CN, Wf):
    """AP with per-window weight = bootstrap multiplicity of its recording. Wf: (R, nfiles)."""
    tp = Wf @ CP; fp = Wf @ CN
    P = tp[:, -1:]; den = tp + fp
    prec = np.where(den > 0, tp / np.where(den > 0, den, 1), 0.0)
    rec = np.where(P > 0, tp / np.where(P > 0, P, 1), 0.0)
    ap = (np.diff(rec, axis=1, prepend=0.0) * prec).sum(1)
    return np.where(P[:, 0] > 0, ap, np.nan)

def weighted_ap_torch(CP, CN, Wf, dev):
    import torch
    CPt = torch.from_numpy(CP).to(dev); CNt = torch.from_numpy(CN).to(dev); out = []
    for c in range(0, len(Wf), 200):
        W = torch.from_numpy(Wf[c:c + 200]).to(dev)
        tp = W @ CPt; fp = W @ CNt; P = tp[:, -1:]; den = tp + fp
        prec = torch.where(den > 0, tp / den.clamp(min=1e-300), torch.zeros_like(tp))
        rec = torch.where(P > 0, tp / P.clamp(min=1e-300), torch.zeros_like(tp))
        drec = torch.diff(rec, dim=1, prepend=torch.zeros_like(rec[:, :1]))
        ap = (drec * prec).sum(1); ap = torch.where(P[:, 0] > 0, ap, torch.full_like(ap, float('nan')))
        out.append(ap.cpu().numpy())
    return np.concatenate(out)

def resample_weights(tokens, rng, R):
    """Recording-level bootstrap stratified by attack token: within each token, draw its k files with replacement."""
    tokens = np.asarray(tokens); W = np.zeros((R, len(tokens)))
    for t in np.unique(tokens):
        idx = np.flatnonzero(tokens == t); k = len(idx)
        draw = rng.integers(0, k, size=(R, k))
        for j in range(k): np.add.at(W, (np.arange(R), idx[draw[:, j]]), 1.0)
    return W

def apply_thr(s, thr):
    return (s >= thr['threshold']) if thr['op'] == '>=' else (s > thr['threshold'])

def macro_f1(y, pred):
    out = []
    for c in (1, 0):
        tp = np.sum((pred == c) & (y == c)); fp = np.sum((pred == c) & (y != c)); fn = np.sum((pred != c) & (y == c))
        out.append(2 * tp / max(2 * tp + fp + fn, 1))
    return float(np.mean(out))

def ci(a, lvl):
    a = a[np.isfinite(a)]; q = (1 - lvl) / 2
    return [float(np.quantile(a, q)), float(np.quantile(a, 1 - q))]

def decide(diff_boot):
    c95, c90 = ci(diff_boot, 0.95), ci(diff_boot, 0.90)
    if c95[0] > 0: d = 'superior'
    elif c95[1] < 0: d = 'inferior'
    elif c90[0] >= -MARGIN and c90[1] <= MARGIN: d = 'practically_equivalent'
    else: d = 'inconclusive'
    a = diff_boot[np.isfinite(diff_boot)]
    p = min(1.0, 2 * min((a <= 0).mean(), (a >= 0).mean()))
    p = max(p, 1.0 / len(a))   # resolution floor
    return {'ci95': c95, 'ci90': c90, 'decision': d, 'ci90_within_margin': bool(c90[0] >= -MARGIN and c90[1] <= MARGIN), 'p_boot_two_sided': float(p),
            'decision_rule': '95% CI excludes 0 -> superior/inferior (checked first); else 90% CI within +-0.02 -> practically_equivalent; else inconclusive'}

def holm(pvals):
    keys = sorted(pvals, key=lambda k: pvals[k]); m = len(keys); adj = {}; run = 0.0
    for i, k in enumerate(keys):
        run = max(run, min(1.0, (m - i) * pvals[k])); adj[k] = run
    return adj

def main(EVAL, OUT, FINAL):
    os.makedirs(OUT, exist_ok=True); rng = np.random.default_rng(BOOT_SEED)
    cells = sorted(glob.glob(os.path.join(EVAL, 'set_*', 'test_0*_scores.npz')))
    R = {'per_cell': {}, 'hypotheses': {}, 'notes': []}; BOOT = {}
    for path in cells:
        st = path.split(os.sep)[-2]; short = os.path.basename(path)[:7]; key = f'{st}/{short}'
        Z = np.load(path); meta = json.load(open(path.replace('_scores.npz', '_meta.json')))
        TH = json.load(open(glob.glob(os.path.join(FINAL, st, 'thresholds.json'))[0]))
        y = Z['y'].astype(np.int8); fid = Z['file_id'].astype(np.int64); hours = meta['hours']
        tokens = [f['token'] for f in meta['files']]
        cr = {'role': ROLE[short], 'windows': int(len(y)), 'pos': int(y.sum()), 'prevalence_chance_ap': float(y.mean()), 'hours': hours,
              'n_files': len(tokens), 'files_per_token': {t: tokens.count(t) for t in sorted(set(tokens))}, 'models': {}}
        Wb = resample_weights(tokens, rng, NBOOT); BOOT[key] = {}
        for m in MODELS:
            S = Z[f'score_{m}'].astype(np.float64); th = TH[m]
            aps = [float(average_precision_score(y, s)) for s in S]
            mr = {'ap_seeds': aps, 'ap_mean': float(np.mean(aps)), 'ap_sd': float(np.std(aps, ddof=1)) if len(aps) > 1 else 0.0}
            mf, rec = [], {1: [], 5: []}; fah = {1: [], 5: []}
            for s in S:
                mf.append(macro_f1(y, apply_thr(s, th['f1']).astype(np.int8)))
                for r in (1, 5):
                    pr = apply_thr(s, th[f'fa{r}']); fp = int(np.sum(pr & (y == 0)))
                    rec[r].append(float(np.mean(pr[y == 1])) if y.sum() else float('nan')); fah[r].append(fp / hours)
            mr['macro_f1_mean'] = float(np.mean(mf)); mr['macro_f1_seeds'] = mf
            for r in (1, 5):
                mr[f'recall_at_{r}FAh_mean'] = float(np.mean(rec[r])); mr[f'achieved_FAh_at_{r}FAh_mean'] = float(np.mean(fah[r]))
                mr[f'allowed_fp_test_{r}FAh'] = int(math.floor(r * hours))
            # per attack token (tokens with >=50 positive windows in the cell)
            fam = {}
            for t in sorted(set(tokens)):
                ti = np.isin(fid, [i for i, tt in enumerate(tokens) if tt == t]); npos = int(y[ti].sum())
                if npos < 50: continue
                fam[t] = {'pos': npos,
                          'ap_token_recordings_mean': float(np.mean([average_precision_score(y[ti], s[ti]) for s in S])),
                          'ap_token_pos_vs_all_cell_neg_mean': float(np.mean([average_precision_score(y[ti | (y == 0)], s[ti | (y == 0)]) for s in S]))}
            mr['per_token'] = fam
            # bootstrap: seed-averaged AP per resample
            bs = np.zeros(NBOOT)
            for s in S:
                CP, CN = weighted_ap_prep(s, y, fid, len(tokens)); acc = np.zeros(NBOOT)
                chk = weighted_ap(CP, CN, np.ones((1, len(tokens))))[0]
                assert abs(chk - average_precision_score(y, s)) < 1e-9, ('weighted AP self-check failed', key, m, chk)
                if DEV:
                    acc = weighted_ap_torch(CP, CN, Wb, DEV)
                    ref = weighted_ap(CP, CN, Wb[:CHUNK]); assert np.allclose(acc[:CHUNK], ref, atol=1e-9, equal_nan=True), 'torch/numpy bootstrap mismatch'
                else:
                    for c in range(0, NBOOT, CHUNK): acc[c:c + CHUNK] = weighted_ap(CP, CN, Wb[c:c + CHUNK])
                bs += acc
            BOOT[key][m] = bs / len(S)
            mr['ap_mean_boot_ci95'] = ci(BOOT[key][m], 0.95)
            cr['models'][m] = mr
        for h, (a, b) in CONTRASTS.items():
            d = BOOT[key][a] - BOOT[key][b]
            cr.setdefault('contrasts', {})[h] = {'diff_point': cr['models'][a]['ap_mean'] - cr['models'][b]['ap_mean'], **decide(d)}
        R['per_cell'][key] = cr
        print(time.strftime('%H:%M:%S'), key, {m: round(cr['models'][m]['ap_mean'], 4) for m in MODELS}, flush=True)
    # B-cell inference
    bkeys = sorted(k for k in R['per_cell'] if k.endswith('test_02'))
    shas = [f['sha256'] for k in bkeys for f in json.load(open(os.path.join(EVAL, k.replace('/', os.sep) + '_meta.json')))['files']]
    assert len(shas) == len(set(shas)), 'B cells share a recording; SHA-256 dedup required'
    strata = {'B_summary': bkeys, 'B_same_manufacturer': [k for k in bkeys if k.startswith('set_01')], 'B_cross_manufacturer': [k for k in bkeys if not k.startswith('set_01')]}
    pv = {}
    for h, (a, b) in CONTRASTS.items():
        for sname, ks in strata.items():
            if not ks: continue
            d = np.mean([BOOT[k][a] - BOOT[k][b] for k in ks], 0)   # independent per-cell resamples = bootstrap stratified by cell
            pt = float(np.mean([R['per_cell'][k]['models'][a]['ap_mean'] - R['per_cell'][k]['models'][b]['ap_mean'] for k in ks]))
            R['hypotheses'].setdefault(h, {})[sname] = {'cells': ks, 'diff_point': pt, **decide(d)}
        if h in SECONDARY: pv[f'{h}/B_summary'] = R['hypotheses'][h]['B_summary']['p_boot_two_sided']
        if h in ['H1'] + SECONDARY:
            for k in bkeys: pv[f'{h}/{k}'] = R['per_cell'][k]['contrasts'][h]['p_boot_two_sided']
    R['holm_family'] = {'members': sorted(pv), 'p_raw': pv, 'p_holm': holm(pv),
                        'note': 'H1 B_summary is the single primary test (not in the family). Bootstrap p-values have resolution 1/2000.'}
    R['notes'] += ['Chance-level PR-AUC = prevalence.', 'Thresholds from pooled OOF scores of fold models, applied to final models (calibration-transfer limitation).',
                   'Per-token AP given two ways: token recordings only; token positives vs all cell negatives.',
                   'set_01/test_04 excluded by design (not scored).']
    json.dump(R, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
    np.savez_compressed(os.path.join(OUT, 'bootstrap_seedavg_ap.npz'), **{f'{k}|{m}': v for k, d in BOOT.items() for m, v in d.items()})
    # compact tables
    L = ['cell\trole\tprev\t' + '\t'.join(MODELS)]
    for k, c in R['per_cell'].items():
        L.append(f"{k}\t{c['role']}\t{c['prevalence_chance_ap']:.4f}\t" + '\t'.join(f"{c['models'][m]['ap_mean']:.4f}±{c['models'][m]['ap_sd']:.4f}" for m in MODELS))
    L.append(''); L.append('hypothesis\tstratum\tdiff\tci95\tci90\tdecision\tp_raw\tp_holm')
    for h, dd in R['hypotheses'].items():
        for sname, v in dd.items():
            ph = R['holm_family']['p_holm'].get(f'{h}/{sname}', '')
            L.append(f"{h}\t{sname}\t{v['diff_point']:+.4f}\t[{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}]\t[{v['ci90'][0]:+.4f},{v['ci90'][1]:+.4f}]\t{v['decision']}\t{v['p_boot_two_sided']:.4f}\t{ph}")
    open(os.path.join(OUT, 'summary.tsv'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--eval', default='/kaggle/working/eval'); ap.add_argument('--out', default='/kaggle/working/stats')
    ap.add_argument('--final', default=None); ap.add_argument('--device', default=None); a = ap.parse_args()
    DEV = a.device
    FINAL = a.final or os.path.dirname(os.path.dirname(glob.glob('/kaggle/input/**/final/set_01/thresholds.json', recursive=True)[0]))
    main(a.eval, a.out, FINAL)
