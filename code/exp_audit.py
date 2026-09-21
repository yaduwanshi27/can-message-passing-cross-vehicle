"""Stage 5c recording-level audit of the FROZEN k05 outputs. No training, no re-scoring, no exclusion of data.
Purpose: test whether B-cell conclusions are robust to recording-level imbalance (2 recordings per attack token; one can dominate positives).
Usage: python exp_audit.py --eval <k05 eval dir> --out /kaggle/working/audit"""
import os, sys, json, glob, argparse, itertools, math
import numpy as np
from sklearn.metrics import average_precision_score

MODELS = ['Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired']
CONTRASTS = {'H1_GS_minus_DeepSets': ('GraphSAGE', 'DeepSets'), 'H1a_GS_minus_rewired': ('GraphSAGE', 'GraphSAGE_rewired'),
             'H2_GS_minus_GRU': ('GraphSAGE', 'GRU'), 'H3_GS_minus_LGBS': ('GraphSAGE', 'LightGBM_S'),
             'ladder_LGBS_minus_LGB': ('LightGBM_S', 'LightGBM')}
MARGIN = 0.02; MC_SUMMARY = 200000; MC_SEED = 20260917

def ap_prep(s, y, fid, nfiles):
    o = np.argsort(-s, kind='stable'); ss = s[o]; ys = y[o].astype(np.float64); fs = fid[o]
    ends = np.r_[np.flatnonzero(ss[1:] != ss[:-1]), len(ss) - 1]
    CP = np.zeros((nfiles, len(ends))); CN = np.zeros((nfiles, len(ends)))
    for f in range(nfiles):
        m = fs == f
        CP[f] = np.cumsum(m * ys)[ends]; CN[f] = np.cumsum(m * (1 - ys))[ends]
    return CP, CN

def ap_w(CP, CN, W, chunk=64):
    out = np.empty(len(W))
    for c in range(0, len(W), chunk):
        w = W[c:c + chunk]
        tp = w @ CP; fp = w @ CN; P = tp[:, -1:]; den = tp + fp
        prec = np.where(den > 0, tp / np.where(den > 0, den, 1), 0.0)
        rec = np.where(P > 0, tp / np.where(P > 0, P, 1), 0.0)
        ap = (np.diff(rec, axis=1, prepend=0.0) * prec).sum(1)
        out[c:c + chunk] = np.where(P[:, 0] > 0, ap, np.nan)
    return out

def exact_token_resamples(tokens):
    """Every distinct token-stratified bootstrap outcome with its probability. For a token with k recordings, the
    multiset of k draws with replacement; probability = multinomial weight / k**k."""
    tokens = np.asarray(tokens); per = []
    for t in sorted(set(tokens.tolist())):
        idx = np.flatnonzero(tokens == t); k = len(idx); opts = {}
        for draw in itertools.product(range(k), repeat=k):
            cnt = tuple(sorted(np.bincount(draw, minlength=k).tolist(), reverse=False))
            key = tuple(np.bincount(draw, minlength=k).tolist())
            opts[key] = opts.get(key, 0) + 1
        per.append([(idx, np.array(key, float), c / float(k ** k)) for key, c in opts.items()])
    W = []; P = []
    for combo in itertools.product(*per):
        w = np.zeros(len(tokens)); p = 1.0
        for idx, cnt, pr in combo:
            w[idx] = cnt; p *= pr
        W.append(w); P.append(p)
    return np.array(W), np.array(P)

def wq(vals, probs, q):
    o = np.argsort(vals); v = vals[o]; c = np.cumsum(probs[o]); c /= c[-1]
    return float(v[np.searchsorted(c, q, side='left').clip(0, len(v) - 1)])

def summarise(vals, probs):
    m = np.isfinite(vals); vals, probs = vals[m], probs[m] / probs[m].sum()
    lo95, hi95, lo90, hi90 = wq(vals, probs, .025), wq(vals, probs, .975), wq(vals, probs, .05), wq(vals, probs, .95)
    if lo95 > 0: d = 'superior'
    elif hi95 < 0: d = 'inferior'
    elif lo90 >= -MARGIN and hi90 <= MARGIN: d = 'practically_equivalent'
    else: d = 'inconclusive'
    p = min(1.0, 2 * min(probs[vals <= 0].sum(), probs[vals >= 0].sum()))
    return {'mean_over_resamples': float((vals * probs).sum()), 'ci95': [lo95, hi95], 'ci90': [lo90, hi90],
            'decision': d, 'p_exact_two_sided': float(p), 'n_distinct_resamples': int(len(vals))}

def main(EVAL, OUT):
    os.makedirs(OUT, exist_ok=True); R = {'cells': {}, 'summary': {}, 'method': {
        'per_recording_ap': 'AP computed on that recording alone (diagnostic only; unstable at low positive counts)',
        'leave_one_out': 'cell AP recomputed with that recording removed (replaces the ill-defined per-recording contribution to a global ranking metric)',
        'exact_bootstrap': 'complete enumeration of the token-stratified recording bootstrap with exact probabilities (replaces 2,000 random draws; same estimator)',
        'no_exclusions': 'no recording is dropped from the frozen results; leave-one-out is diagnostic'}}
    per_cell_dist = {}
    for path in sorted(glob.glob(os.path.join(EVAL, 'set_*', 'test_02_scores.npz'))):
        st = path.split(os.sep)[-2]; key = f'{st}/test_02'
        Z = np.load(path); meta = json.load(open(path.replace('_scores.npz', '_meta.json')))
        y = Z['y'].astype(np.int8); fid = Z['file_id'].astype(np.int64); files = meta['files']; nf = len(files)
        tokens = [f['token'] for f in files]
        S = {m: Z[f'score_{m}'].astype(np.float64) for m in MODELS}
        cell = {'files': [], 'aggregate': {}, 'leave_one_out': {}, 'exact_bootstrap': {}, 'seed_vs_recording_variability': {}}
        tot_pos = int(y.sum())
        for i, f in enumerate(files):
            ix = fid == i; rec = {'file': f['file'], 'token': f['token'], 'windows': int(ix.sum()), 'pos': int(y[ix].sum()),
                                  'share_of_cell_positives': round(float(y[ix].sum()) / max(tot_pos, 1), 4),
                                  'prevalence': round(float(y[ix].mean()), 5), 'hours': round(f['hours'], 4), 'ap_mean': {}, 'ap_sd': {}}
            for m in MODELS:
                a = [average_precision_score(y[ix], s[ix]) if y[ix].sum() > 0 else float('nan') for s in S[m]]
                rec['ap_mean'][m] = round(float(np.mean(a)), 4); rec['ap_sd'][m] = round(float(np.std(a, ddof=1)) if len(a) > 1 else 0.0, 4)
            rec['contrasts'] = {h: round(rec['ap_mean'][a] - rec['ap_mean'][b], 4) for h, (a, b) in CONTRASTS.items()}
            cell['files'].append(rec)
        agg = {m: float(np.mean([average_precision_score(y, s) for s in S[m]])) for m in MODELS}
        cell['aggregate'] = {'ap_mean': {m: round(agg[m], 4) for m in MODELS},
                             'contrasts': {h: round(agg[a] - agg[b], 4) for h, (a, b) in CONTRASTS.items()},
                             'windows': int(len(y)), 'pos': tot_pos, 'prevalence': round(float(y.mean()), 5)}
        for i, f in enumerate(files):   # leave-one-recording-out
            keep = fid != i
            if y[keep].sum() == 0: continue
            a2 = {m: float(np.mean([average_precision_score(y[keep], s[keep]) for s in S[m]])) for m in MODELS}
            cell['leave_one_out'][f['file']] = {'ap_mean': {m: round(a2[m], 4) for m in MODELS},
                                                'contrasts': {h: round(a2[a] - a2[b], 4) for h, (a, b) in CONTRASTS.items()},
                                                'delta_vs_full': {h: round((a2[a] - a2[b]) - (agg[a] - agg[b]), 4) for h, (a, b) in CONTRASTS.items()}}
        W, P = exact_token_resamples(tokens)
        B = {}
        for m in MODELS:
            acc = np.zeros(len(W))
            for s in S[m]:
                CP, CN = ap_prep(s, y, fid, nf)
                chk = ap_w(CP, CN, np.ones((1, nf)))[0]
                assert abs(chk - average_precision_score(y, s)) < 1e-9
                acc += ap_w(CP, CN, W)
            B[m] = acc / len(S[m])
        per_cell_dist[key] = {'W_prob': P, 'ap': B}
        for h, (a, b) in CONTRASTS.items():
            cell['exact_bootstrap'][h] = {'point_full_sample': round(agg[a] - agg[b], 4), **summarise(B[a] - B[b], P)}
        for m in MODELS:
            sd_seed = float(np.std([average_precision_score(y, s) for s in S[m]], ddof=1)) if len(S[m]) > 1 else 0.0
            sd_rec = float(np.sqrt(((B[m] - (B[m] * P).sum()) ** 2 * P).sum()))
            cell['seed_vs_recording_variability'][m] = {'sd_across_seeds': round(sd_seed, 4), 'sd_across_recording_resamples': round(sd_rec, 4)}
        R['cells'][key] = cell
        print(key, 'exact resamples', len(W), 'aggregate', cell['aggregate']['contrasts'], flush=True)
    keys = sorted(per_cell_dist)
    rng = np.random.default_rng(MC_SEED)
    draws = {k: rng.choice(len(per_cell_dist[k]['W_prob']), size=MC_SUMMARY, p=per_cell_dist[k]['W_prob'] / per_cell_dist[k]['W_prob'].sum()) for k in keys}
    strata = {'B_summary': keys, 'B_same_manufacturer': [k for k in keys if k.startswith('set_01')], 'B_cross_manufacturer': [k for k in keys if not k.startswith('set_01')]}
    unif = np.full(MC_SUMMARY, 1.0 / MC_SUMMARY)
    for h, (a, b) in CONTRASTS.items():
        for sname, ks in strata.items():
            d = np.mean([per_cell_dist[k]['ap'][a][draws[k]] - per_cell_dist[k]['ap'][b][draws[k]] for k in ks], 0)
            pt = float(np.mean([R['cells'][k]['aggregate']['contrasts'][h] for k in ks]))
            R['summary'].setdefault(h, {})[sname] = {'point_full_sample': round(pt, 4), 'cells': ks,
                                                     **summarise(d, unif), 'note': f'{MC_SUMMARY} draws from the EXACT per-cell resample distributions'}
    json.dump(R, open(os.path.join(OUT, 'audit.json'), 'w'), indent=1)
    # readable tables
    L = []
    for k, c in R['cells'].items():
        L.append(f"\n== {k}  windows {c['aggregate']['windows']}  pos {c['aggregate']['pos']}  prevalence {c['aggregate']['prevalence']}")
        L.append('recording\ttoken\twin\tpos\tposshare\t' + '\t'.join(MODELS) + '\tGS-DS\tGS-rew')
        for f in c['files']:
            L.append(f"{f['file']}\t{f['token']}\t{f['windows']}\t{f['pos']}\t{f['share_of_cell_positives']}\t" + '\t'.join(f"{f['ap_mean'][m]:.3f}" for m in MODELS)
                     + f"\t{f['contrasts']['H1_GS_minus_DeepSets']:+.3f}\t{f['contrasts']['H1a_GS_minus_rewired']:+.3f}")
        L.append('AGGREGATE\t\t\t\t\t' + '\t'.join(f"{c['aggregate']['ap_mean'][m]:.3f}" for m in MODELS)
                 + f"\t{c['aggregate']['contrasts']['H1_GS_minus_DeepSets']:+.3f}\t{c['aggregate']['contrasts']['H1a_GS_minus_rewired']:+.3f}")
        L.append('leave-one-out (cell AP without that recording) — GS-DS / GS-rewired, and change vs full cell:')
        for fn, v in c['leave_one_out'].items():
            L.append(f"  drop {fn}\tGS-DS {v['contrasts']['H1_GS_minus_DeepSets']:+.3f} ({v['delta_vs_full']['H1_GS_minus_DeepSets']:+.3f})"
                     f"\tGS-rew {v['contrasts']['H1a_GS_minus_rewired']:+.3f} ({v['delta_vs_full']['H1a_GS_minus_rewired']:+.3f})"
                     f"\tGS-LGB+S {v['contrasts']['H3_GS_minus_LGBS']:+.3f} ({v['delta_vs_full']['H3_GS_minus_LGBS']:+.3f})")
        L.append('exact token-stratified bootstrap:')
        for h, v in c['exact_bootstrap'].items():
            L.append(f"  {h}\tpoint {v['point_full_sample']:+.4f}\tmean {v['mean_over_resamples']:+.4f}\tci95 [{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}]\tci90 [{v['ci90'][0]:+.4f},{v['ci90'][1]:+.4f}]\t{v['decision']}\tp {v['p_exact_two_sided']:.4f}\tN {v['n_distinct_resamples']}")
        L.append('variability (SD across seeds | SD across recording resamples):')
        L.append('  ' + '  '.join(f"{m} {v['sd_across_seeds']:.3f}|{v['sd_across_recording_resamples']:.3f}" for m, v in c['seed_vs_recording_variability'].items()))
    L.append('\n== B summary / strata (exact per-cell distributions)')
    L.append('contrast\tstratum\tpoint\tmean\tci95\tci90\tdecision\tp')
    for h, dd in R['summary'].items():
        for sname, v in dd.items():
            L.append(f"{h}\t{sname}\t{v['point_full_sample']:+.4f}\t{v['mean_over_resamples']:+.4f}\t[{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}]\t[{v['ci90'][0]:+.4f},{v['ci90'][1]:+.4f}]\t{v['decision']}\t{v['p_exact_two_sided']:.4f}")
    open(os.path.join(OUT, 'audit.tsv'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--eval', required=True); ap.add_argument('--out', default='/kaggle/working/audit'); a = ap.parse_args()
    main(a.eval, a.out)
