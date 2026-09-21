"""Stage 7 statistics. For each robustness mode: per-cell PR-AUC (5 seeds), per-attack-token PR-AUC (>=50 positives), exact token-stratified
recording bootstrap on the B cells (k06 code, unchanged), and the change versus the FROZEN k05 values. 'span' = negatives-in-attack-span
sensitivity built from the frozen k05 scores (evaluation-only). Nothing here alters RESULTS_FROZEN_v1.0."""
import os, sys, json, glob, shutil, argparse, io, contextlib
import numpy as np
from sklearn.metrics import average_precision_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exp_audit
MODELS = ['Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired']
H = ['H1_GS_minus_DeepSets', 'H1a_GS_minus_rewired', 'H2_GS_minus_GRU', 'H3_GS_minus_LGBS', 'ladder_LGBS_minus_LGB']

def build_span(k05_eval, out):
    """Remove negative windows lying between the first and last positive window of each recording (B cells only)."""
    rep = {}
    for p in sorted(glob.glob(os.path.join(k05_eval, 'set_*', 'test_02_scores.npz'))):
        st = p.split(os.sep)[-2]; os.makedirs(os.path.join(out, st), exist_ok=True)
        Z = dict(np.load(p)); y = Z['y']; fid = Z['file_id'].astype(int); starts = Z['starts']; keep = np.ones(len(y), bool)
        for f in np.unique(fid):
            ix = np.flatnonzero(fid == f); pos = ix[y[ix] == 1]
            if len(pos) == 0: continue
            lo, hi = starts[pos].min(), starts[pos].max()
            drop = ix[(y[ix] == 0) & (starts[ix] > lo) & (starts[ix] < hi)]; keep[drop] = False
        np.savez_compressed(os.path.join(out, st, 'test_02_scores.npz'), **{k: v[keep] if v.ndim == 1 else v[:, keep] for k, v in Z.items()})
        shutil.copy(p.replace('_scores.npz', '_meta.json'), os.path.join(out, st, 'test_02_meta.json'))
        rep[f'{st}/test_02'] = {'windows_before': int(len(y)), 'negatives_removed': int((~keep).sum()), 'windows_after': int(keep.sum()), 'positives': int(y.sum())}
    return rep

def cell_tables(d):
    R = {}
    for p in sorted(glob.glob(os.path.join(d, 'set_*', 'test_0*_scores.npz'))):
        st = p.split(os.sep)[-2]; key = f'{st}/{os.path.basename(p)[:7]}'
        Z = np.load(p); meta = json.load(open(p.replace('_scores.npz', '_meta.json')))
        y = Z['y']; fid = Z['file_id'].astype(int); toks = [f['token'] for f in meta['files']]
        c = {'windows': int(len(y)), 'pos': int(y.sum()), 'prevalence': float(y.mean()), 'models': {}, 'per_token': {}}
        for m in MODELS:
            a = [average_precision_score(y, s) for s in Z[f'score_{m}']]
            c['models'][m] = {'ap_mean': float(np.mean(a)), 'ap_sd': float(np.std(a, ddof=1)) if len(a) > 1 else 0.0}
        for t in sorted(set(toks)):
            ti = np.isin(fid, [i for i, tt in enumerate(toks) if tt == t])
            if y[ti].sum() < 50: continue
            c['per_token'][t] = {'pos': int(y[ti].sum()), **{m: float(np.mean([average_precision_score(y[ti], s[ti]) for s in Z[f'score_{m}']])) for m in MODELS}}
        R[key] = c
    return R

def main(ROBUST, K05_EVAL, K05_STATS, AUDIT_K06, OUT):
    os.makedirs(OUT, exist_ok=True)
    frozen = json.load(open(os.path.join(K05_STATS, 'results.json')))['per_cell']
    frozen_ex = json.load(open(os.path.join(AUDIT_K06, 'audit.json')))
    RES = {'span_filter': build_span(K05_EVAL, os.path.join(OUT, 'span_eval'))}
    dirs = {'span': os.path.join(OUT, 'span_eval')}
    for m in ('d4', 'w32', 'w128'):
        if glob.glob(os.path.join(ROBUST, m, 'set_*', 'test_02_scores.npz')): dirs[m] = os.path.join(ROBUST, m)
    L = []
    for mode, d in dirs.items():
        cells = cell_tables(d)
        n_b = len(glob.glob(os.path.join(d, 'set_*', 'test_02_scores.npz')))
        with contextlib.redirect_stdout(io.StringIO()):
            exp_audit.main(d, os.path.join(OUT, f'audit_{mode}'))
        A = json.load(open(os.path.join(OUT, f'audit_{mode}', 'audit.json')))
        RES[mode] = {'n_B_cells': n_b, 'cells': cells, 'exact_B': {h: A['summary'][h] for h in H},
                     'exact_B_per_cell': {k: {h: c['exact_bootstrap'][h] for h in H} for k, c in A['cells'].items()},
                     'delta_vs_frozen_ap': {k: {m: c['models'][m]['ap_mean'] - frozen[k]['models'][m]['ap_mean'] for m in MODELS} for k, c in cells.items() if k in frozen}}
        L.append(f'\n==== MODE {mode}  (B cells: {n_b})')
        L.append('cell\t' + '\t'.join(MODELS) + '\t| change vs frozen: ' + ' '.join(MODELS))
        for k, c in cells.items():
            dv = RES[mode]['delta_vs_frozen_ap'].get(k, {})
            L.append(k + '\t' + '\t'.join(f"{c['models'][m]['ap_mean']:.4f}" for m in MODELS) + '\t| ' + ' '.join(f"{dv.get(m, float('nan')):+.4f}" for m in MODELS))
        L.append('exact-bootstrap B contrasts (frozen value in brackets):')
        for h in H:
            for sname in ('B_summary', 'B_same_manufacturer', 'B_cross_manufacturer'):
                v = A['summary'][h].get(sname)
                if not v: continue
                fz = frozen_ex['summary'][h][sname]
                L.append(f"  {h}\t{sname}\t{v['point_full_sample']:+.4f} [{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}] {v['decision']} p={v['p_exact_two_sided']:.4f}\t(frozen {fz['point_full_sample']:+.4f} {fz['decision']})")
        L.append('per-cell H1 / H1a: ' + '; '.join(f"{k}: {v['H1_GS_minus_DeepSets']['point_full_sample']:+.4f} {v['H1_GS_minus_DeepSets']['decision']} / {v['H1a_GS_minus_rewired']['point_full_sample']:+.4f} {v['H1a_GS_minus_rewired']['decision']}"
                                           for k, v in RES[mode]['exact_B_per_cell'].items()))
        L.append('per-token PR-AUC on B cells (>=50 positives):')
        for k, c in cells.items():
            if not k.endswith('test_02'): continue
            for t, v in c['per_token'].items():
                L.append(f"  {k}\t{t}\t{v['pos']}\t" + ' '.join(f"{v[m]:.3f}" for m in MODELS))
    L.insert(0, 'span filter: ' + json.dumps(RES['span_filter']))
    json.dump(RES, open(os.path.join(OUT, 'robust_results.json'), 'w'), indent=1)
    open(os.path.join(OUT, 'robust_summary.tsv'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    for a in ('robust', 'k05_eval', 'k05_stats', 'k06_audit', 'out'): ap.add_argument('--' + a, required=True)
    a = ap.parse_args(); main(a.robust, a.k05_eval, a.k05_stats, a.k06_audit, a.out)
