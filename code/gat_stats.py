"""k09 statistics (STAGE2_DESIGN_ADDENDUM_v1.2_GAT §5). Reads k09 GAT/GAT_rewired B-cell scores and the FROZEN k05 B-cell scores of
DeepSets and GraphSAGE (identical windows, asserted). Exact enumeration of the attack-family-stratified recording bootstrap (k06 code),
B summary from 200,000 draws of the exact per-cell distributions, Holm over the three B-summary tests. No fitting, no selection.
Usage: python gat_stats.py --gat /kaggle/working/gat --k05_eval <k05 eval dir> --out /kaggle/working/gat_stats"""
import os, sys, json, glob, argparse, math
import numpy as np
from sklearn.metrics import average_precision_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_audit import ap_prep, ap_w, exact_token_resamples, summarise

MODELS = ['DeepSets', 'GraphSAGE', 'GAT', 'GAT_rewired']
CONTRASTS = {'E1_GAT_minus_DeepSets': ('GAT', 'DeepSets'), 'E1a_GAT_minus_rewired': ('GAT', 'GAT_rewired'), 'E2_GAT_minus_GraphSAGE': ('GAT', 'GraphSAGE')}
MC_SUMMARY = 200000; MC_SEED = 20260917

def apply_thr(s, thr): return (s >= thr['threshold']) if thr['op'] == '>=' else (s > thr['threshold'])
def macro_f1(y, pred):
    out = []
    for c in (1, 0):
        tp = np.sum((pred == c) & (y == c)); fp = np.sum((pred == c) & (y != c)); fn = np.sum((pred != c) & (y == c))
        out.append(2 * tp / max(2 * tp + fp + fn, 1))
    return float(np.mean(out))
def holm(p):
    ks = sorted(p, key=lambda k: p[k]); m = len(ks); adj = {}; run = 0.0
    for i, k in enumerate(ks): run = max(run, min(1.0, (m - i) * p[k])); adj[k] = run
    return adj

def main(GAT, K05, OUT):
    os.makedirs(OUT, exist_ok=True); R = {'cells': {}, 'summary': {}, 'holm_B_summary': {}}; dist = {}
    for path in sorted(glob.glob(os.path.join(GAT, 'set_*', 'test_02_scores.npz'))):
        st = path.split(os.sep)[-2]; key = f'{st}/test_02'
        G = np.load(path); meta = json.load(open(path.replace('_scores.npz', '_meta.json')))
        K = np.load(os.path.join(K05, st, 'test_02_scores.npz'))
        y = G['y'].astype(np.int8); fid = G['file_id'].astype(np.int64)
        assert np.array_equal(K['y'], G['y']) and np.array_equal(K['file_id'], G['file_id']) and np.array_equal(K['starts'], G['starts']), 'window mismatch'
        S = {'DeepSets': K['score_DeepSets'], 'GraphSAGE': K['score_GraphSAGE'], 'GAT': G['score_GAT'], 'GAT_rewired': G['score_GAT_rewired']}
        S = {m: v.astype(np.float64) for m, v in S.items()}
        files = meta['files']; nf = len(files); tokens = [f['token'] for f in files]; hours = meta['hours']
        TH = json.load(open(os.path.join(GAT, st, 'thresholds.json')))
        c = {'windows': int(len(y)), 'pos': int(y.sum()), 'prevalence': float(y.mean()), 'hours': hours, 'models': {}, 'exact_bootstrap': {}, 'leave_one_out': {}}
        for m in MODELS:
            aps = [float(average_precision_score(y, s)) for s in S[m]]
            mr = {'ap_mean': float(np.mean(aps)), 'ap_sd': float(np.std(aps, ddof=1)) if len(aps) > 1 else 0.0, 'ap_seeds': aps}
            if m in TH:   # operating points only for the new models (k05 already reports the others)
                th = TH[m]; mf = []; rec = {1: [], 5: []}; fah = {1: [], 5: []}
                for s in S[m]:
                    mf.append(macro_f1(y, apply_thr(s, th['f1']).astype(np.int8)))
                    for r in (1, 5):
                        pr = apply_thr(s, th[f'fa{r}']); rec[r].append(float(np.mean(pr[y == 1]))); fah[r].append(int(np.sum(pr & (y == 0))) / hours)
                mr.update({'macro_f1_mean': float(np.mean(mf)), **{f'recall_at_{r}FAh_mean': float(np.mean(rec[r])) for r in (1, 5)},
                           **{f'achieved_FAh_at_{r}FAh_mean': float(np.mean(fah[r])) for r in (1, 5)}})
            fam = {}
            for t in sorted(set(tokens)):
                ti = np.isin(fid, [i for i, tt in enumerate(tokens) if tt == t]); npos = int(y[ti].sum())
                if npos >= 50: fam[t] = {'pos': npos, 'ap_token_recordings_mean': float(np.mean([average_precision_score(y[ti], s[ti]) for s in S[m]]))}
            mr['per_token'] = fam; c['models'][m] = mr
        agg = {m: c['models'][m]['ap_mean'] for m in MODELS}
        c['point'] = {h: agg[a] - agg[b] for h, (a, b) in CONTRASTS.items()}
        for i, f in enumerate(files):
            keep = fid != i
            if y[keep].sum() == 0: continue
            a2 = {m: float(np.mean([average_precision_score(y[keep], s[keep]) for s in S[m]])) for m in MODELS}
            c['leave_one_out'][f['file']] = {h: round(a2[a] - a2[b], 4) for h, (a, b) in CONTRASTS.items()}
        W, P = exact_token_resamples(tokens); B = {}
        for m in MODELS:
            acc = np.zeros(len(W))
            for s in S[m]:
                CP, CN = ap_prep(s, y, fid, nf)
                assert abs(ap_w(CP, CN, np.ones((1, nf)))[0] - average_precision_score(y, s)) < 1e-9
                acc += ap_w(CP, CN, W)
            B[m] = acc / len(S[m])
        dist[key] = {'P': P, 'ap': B}
        for h, (a, b) in CONTRASTS.items():
            c['exact_bootstrap'][h] = {'point_full_sample': round(c['point'][h], 4), **summarise(B[a] - B[b], P)}
        R['cells'][key] = c
        print(key, {m: round(agg[m], 4) for m in MODELS}, {h: v['decision'] for h, v in c['exact_bootstrap'].items()}, flush=True)
    keys = sorted(dist); rng = np.random.default_rng(MC_SEED)
    draws = {k: rng.choice(len(dist[k]['P']), size=MC_SUMMARY, p=dist[k]['P'] / dist[k]['P'].sum()) for k in keys}
    strata = {'B_summary': keys, 'B_same_manufacturer': [k for k in keys if k.startswith('set_01')], 'B_cross_manufacturer': [k for k in keys if not k.startswith('set_01')]}
    unif = np.full(MC_SUMMARY, 1.0 / MC_SUMMARY)
    for h, (a, b) in CONTRASTS.items():
        for sn, ks in strata.items():
            d = np.mean([dist[k]['ap'][a][draws[k]] - dist[k]['ap'][b][draws[k]] for k in ks], 0)
            R['summary'].setdefault(h, {})[sn] = {'point_full_sample': round(float(np.mean([R['cells'][k]['point'][h] for k in ks])), 4), **summarise(d, unif)}
    R['holm_B_summary'] = holm({h: max(R['summary'][h]['B_summary']['p_exact_two_sided'], 1.0 / MC_SUMMARY) for h in CONTRASTS})
    json.dump(R, open(os.path.join(OUT, 'gat_stats.json'), 'w'), indent=1)
    L = ['cell\t' + '\t'.join(MODELS)]
    for k, c in R['cells'].items():
        L.append(k + '\t' + '\t'.join(f"{c['models'][m]['ap_mean']:.4f}±{c['models'][m]['ap_sd']:.4f}" for m in MODELS))
    L.append('\ncontrast\tstratum\tpoint\tci95\tci90\tdecision\tp_exact\tholm(B summary)')
    for h, dd in R['summary'].items():
        for sn, v in dd.items():
            L.append(f"{h}\t{sn}\t{v['point_full_sample']:+.4f}\t[{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}]\t[{v['ci90'][0]:+.4f},{v['ci90'][1]:+.4f}]\t{v['decision']}\t{v['p_exact_two_sided']:.4f}\t"
                     + (f"{R['holm_B_summary'][h]:.4f}" if sn == 'B_summary' else ''))
    L.append('\nper-cell exact bootstrap')
    for k, c in R['cells'].items():
        for h, v in c['exact_bootstrap'].items():
            L.append(f"{k}\t{h}\t{v['point_full_sample']:+.4f}\t[{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}]\t{v['decision']}\tp {v['p_exact_two_sided']:.4f}")
    L.append('\noperating points (GAT, GAT_rewired): macroF1 | recall@1 | FA/h@1 | recall@5 | FA/h@5')
    for k, c in R['cells'].items():
        for m in ('GAT', 'GAT_rewired'):
            v = c['models'][m]
            L.append(f"{k}\t{m}\t{v['macro_f1_mean']:.3f}\t{v['recall_at_1FAh_mean']:.3f}\t{v['achieved_FAh_at_1FAh_mean']:.1f}\t{v['recall_at_5FAh_mean']:.3f}\t{v['achieved_FAh_at_5FAh_mean']:.1f}")
    L.append('\nper-family AP (token recordings only): ' + ' | '.join(MODELS))
    for k, c in R['cells'].items():
        for t in c['models']['GAT']['per_token']:
            L.append(f"{k}\t{t}\t{c['models']['GAT']['per_token'][t]['pos']}\t" + '\t'.join(f"{c['models'][m]['per_token'][t]['ap_token_recordings_mean']:.3f}" for m in MODELS))
    L.append('\nleave-one-recording-out E1 (GAT - DeepSets)')
    for k, c in R['cells'].items():
        L.append(k + '\t' + '  '.join(f"{fn}:{v['E1_GAT_minus_DeepSets']:+.3f}" for fn, v in c['leave_one_out'].items()))
    open(os.path.join(OUT, 'gat_stats.tsv'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--gat', required=True); ap.add_argument('--k05_eval', required=True); ap.add_argument('--out', default='/kaggle/working/gat_stats')
    a = ap.parse_args(); main(a.gat, a.k05_eval, a.out)
