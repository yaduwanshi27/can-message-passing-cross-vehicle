"""Stage 4 final models (STAGE2_DESIGN_FROZEN_v1.1 §8). Reads ONLY train_01 + k03 tuning outputs. No test data.
Usage: python exp_final.py --sets set_01,set_03 --device cuda:0"""
import os, sys, re, json, time, glob, hashlib, argparse, traceback, zipfile, math
import numpy as np, torch
from sklearn.metrics import precision_recall_curve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feats, models

ap = argparse.ArgumentParser()
ap.add_argument('--sets', required=True); ap.add_argument('--device', default='cuda:0')
ap.add_argument('--out', default='/kaggle/working/final'); ap.add_argument('--lgb_threads', type=int, default=2)
ap.add_argument('--seeds', default='0,1,2,3,4')
args = ap.parse_args()
DEV = args.device; OUT = args.out; os.makedirs(OUT, exist_ok=True)
SETS = args.sets.split(','); SEEDS = [int(s) for s in args.seeds.split(',')]; BS = 1024
ZIP = glob.glob('/kaggle/input/**/can-train-and-test-v1.zip', recursive=True)[0]
HASHES = glob.glob('/kaggle/input/**/file_hashes_sha256.csv', recursive=True)[0]
DATA = '/kaggle/temp/data'
LOG = open(os.path.join(OUT, f'log_{"_".join(SETS)}.txt'), 'a')
def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a); print(s, flush=True); LOG.write(s + '\n'); LOG.flush()

def extract_train(st):
    H = {}
    for line in open(HASHES).read().strip().split('\n')[1:]:
        rel, size, sha = line.split(','); H[rel] = (int(size), sha)
    os.makedirs(DATA, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        names = [n for n in z.namelist() if n.startswith(f'can-train-and-test/{st}/train_01/') and n.endswith('.csv')]
        assert names and all('/train_01/' in n for n in names)
        for n in names:
            if not os.path.exists(os.path.join(DATA, n)): z.extract(n, DATA)
    files = sorted(glob.glob(os.path.join(DATA, 'can-train-and-test', st, 'train_01', '*.csv')))
    for p in files:
        rel = p.split('can-train-and-test/')[1]; hh = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(8 << 20), b''): hh.update(b)
        assert (os.path.getsize(p), hh.hexdigest()) == H[rel], 'hash mismatch ' + rel
    return files

NF, NN, NG = len(feats.FRAME_NAMES), len(feats.NODE_NAMES), len(feats.GLOBAL_NAMES)
def make(name, h, drop):
    if name in ('GraphSAGE', 'GraphSAGE_rewired'): return models.GraphSAGE(NN, h, NG, drop)
    if name == 'DeepSets': return models.DeepSets(NN, h, NG, drop)
    if name == 'GRU': return models.GRUNet(NF, h, NG, drop)

def flat_features(D, with_struct):
    m = D['nmask'][..., None]; x = D['node'].astype(np.float32); cnt = m.sum(1).clip(1)
    mean = (x * m).sum(1) / cnt; std = np.sqrt(((x - mean[:, None]) ** 2 * m).sum(1) / cnt)
    mn = np.where(m, x, np.inf).min(1); mx = np.where(m, x, -np.inf).max(1)
    X = [mean, std, mn, mx, D['glob']]
    if with_struct: X.append(D['struct'])
    return np.concatenate(X, 1).astype(np.float32)

def norm_stats_np(D):
    f = D['frame'].astype(np.float32).reshape(-1, NF); msk = D['nmask'].reshape(-1)
    n = D['node'].astype(np.float32).reshape(-1, NN)[msk]
    return {'fm': f.mean(0), 'fs': f.std(0) + 1e-6, 'nm': n.mean(0), 'ns': n.std(0) + 1e-6, 'gm': D['glob'].mean(0), 'gs': D['glob'].std(0) + 1e-6}

def to_gpu(D, N):
    T = lambda a: torch.tensor(a, dtype=torch.float32, device=DEV)
    fm, fs, nm_, ns, gm, gs = T(N['fm']), T(N['fs']), T(N['nm']), T(N['ns']), T(N['gm']), T(N['gs'])
    out = {}
    out['frame'] = ((torch.from_numpy(D['frame'].astype(np.float32)).to(DEV) - fm) / fs).half()
    msk = torch.from_numpy(D['nmask']).to(DEV)
    out['node'] = (((torch.from_numpy(D['node'].astype(np.float32)).to(DEV) - nm_) / ns) * msk.unsqueeze(-1)).half()
    out['nmask'] = msk; out['glob'] = (torch.from_numpy(D['glob']).to(DEV) - gm) / gs
    out['src'] = torch.from_numpy(D['src']).to(DEV); out['dst'] = torch.from_numpy(D['dst']).to(DEV)
    out['y'] = torch.from_numpy(D['y'].astype(np.float32)).to(DEV)
    return out

def batch(T, ix, rewire, gen):
    b = {'frame': T['frame'][ix].float(), 'node': T['node'][ix].float(), 'nmask': T['nmask'][ix], 'glob': T['glob'][ix]}
    dst = T['dst'][ix]
    if rewire: dst = models.rewire_dst(dst, gen)
    b['adj'] = models.build_adj(T['src'][ix], dst, len(ix), DEV)
    return b

def thresholds_from_oof(scores, y, val_hours):
    neg = np.sort(scores[y == 0])[::-1]; pos = scores[y == 1]
    out = {'val_hours': val_hours, 'n_val_windows': int(len(y)), 'n_val_pos': int(y.sum())}
    p, r, t = precision_recall_curve(y, scores)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    i = int(np.argmax(f1))
    out['f1'] = {'threshold': float(t[i]), 'op': '>=', 'oof_f1': float(f1[i]), 'oof_precision': float(p[i]), 'oof_recall': float(r[i])}
    for rate in (1, 5):
        k = int(math.floor(rate * val_hours))
        thr = float(neg[k]) if k < len(neg) else float(neg[-1]) - 1e-6
        fp = int((neg > thr).sum()); rec = float((pos > thr).mean()) if len(pos) else float('nan')
        out[f'fa{rate}'] = {'threshold': thr, 'op': '>', 'allowed_fp': k, 'oof_fp': fp, 'oof_recall': rec}
    return out

def run_set(st):
    sd = os.path.join(OUT, st); os.makedirs(sd, exist_ok=True)
    if os.path.exists(os.path.join(sd, 'final_meta.json')):
        log(st, 'already done'); return
    tsel = glob.glob(f'/kaggle/input/**/tune/{st}/selection.json', recursive=True)[0]
    SEL = json.load(open(tsel)); OOF = np.load(os.path.join(os.path.dirname(tsel), 'oof_scores.npz'))
    t0 = time.time(); files = extract_train(st); log(st, 'train files', len(files), 'verify s', round(time.time() - t0, 1))
    t0 = time.time(); F = {}; hours = 0.0
    for p in files:
        d = feats.windows_for_file(p, 32); d['struct'] = feats.structural_features(d['src'], d['dst'], d['nmask']); F[p] = d
        hours += float(d['t1'].max() - d['t0'].min()) / 3600.0
    keys = ['frame', 'node', 'nmask', 'src', 'dst', 'glob', 'y', 'struct']
    D = {k: np.concatenate([F[p][k] for p in files]) for k in keys}
    log(st, 'features s', round(time.time() - t0, 1), 'windows', len(D['y']), 'pos', int(D['y'].sum()), 'train hours', round(hours, 3))
    # thresholds from pooled out-of-fold validation scores (tuning, seed 0)
    y_oof = np.concatenate([OOF['y_f1'], OOF['y_f2']]).astype(np.int8)
    TH = {}
    for name in ('Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired'):
        s = np.concatenate([OOF[f'{name}_f1'], OOF[f'{name}_f2']]).astype(np.float64)
        TH[name] = thresholds_from_oof(s, y_oof, hours)
        log(st, 'thresholds', name, {k: TH[name][k] for k in ('f1', 'fa1', 'fa5')})
    json.dump(TH, open(os.path.join(sd, 'thresholds.json'), 'w'), indent=1)
    N = norm_stats_np(D); np.savez(os.path.join(sd, 'norm_stats.npz'), **N)
    META = {'set': st, 'train_files': [os.path.basename(p) for p in files], 'train_windows': int(len(D['y'])), 'train_pos': int(D['y'].sum()),
            'train_hours': hours, 'seeds': SEEDS, 'models': {}}
    META['models']['Rule'] = {'feature_index': SEL['Rule']['feature_index'], 'sign': SEL['Rule']['sign'], 'layout': '56-feature LightGBM layout'}
    # LightGBM / LightGBM+S
    import lightgbm as lgb
    for name, ws in (('LightGBM', False), ('LightGBM_S', True)):
        X = flat_features(D, ws); y = D['y']; pos = y.sum(); neg = len(y) - pos
        rec = {'config': SEL[name]['config'], 'n_estimators': SEL[name]['final_epochs'], 'n_features': int(X.shape[1]), 'seeds': {}}
        for seed in SEEDS:
            t = time.time()
            clf = lgb.LGBMClassifier(n_estimators=SEL[name]['final_epochs'], scale_pos_weight=neg / max(pos, 1), n_jobs=args.lgb_threads, verbose=-1, random_state=seed, **SEL[name]['config'])
            clf.fit(X, y)
            clf.booster_.save_model(os.path.join(sd, f'{name}_seed{seed}.txt'))
            rec['seeds'][seed] = {'fit_s': round(time.time() - t, 1)}
        META['models'][name] = rec; log(st, name, 'saved', rec['seeds'])
    # neural
    T = to_gpu(D, N); n = len(D['y'])
    pos = float(T['y'].sum()); neg = n - pos
    for name in ('DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired'):
        sel = SEL[name]; cfg = sel['config']; h = sel['hidden']; E = sel['final_epochs']
        rec = {'config': cfg, 'hidden': h, 'epochs': E, 'seeds': {}}
        for seed in SEEDS:
            try:
                torch.manual_seed(seed); np.random.seed(seed)
                gen = torch.Generator(device=DEV); gen.manual_seed(seed)
                m = make(name, h, cfg['dropout']).to(DEV)
                opt = torch.optim.AdamW(m.parameters(), lr=cfg['lr'])
                lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(neg / max(pos, 1.0), device=DEV))
                rew = name == 'GraphSAGE_rewired'; losses = []; t = time.time()
                for ep in range(E):
                    m.train(); perm = torch.randperm(n, device=DEV, generator=gen); tot = 0.0
                    for s in range(0, n, BS):
                        ix = perm[s:s + BS]
                        loss = lossf(m(batch(T, ix, rew, gen)), T['y'][ix]); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(ix)
                    losses.append(round(tot / n, 6))
                torch.save(m.state_dict(), os.path.join(sd, f'{name}_seed{seed}.pt'))
                rec['seeds'][seed] = {'train_loss': losses, 'fit_s': round(time.time() - t, 1), 'params': models.nparams(m)}
            except Exception as e:
                rec['seeds'][seed] = {'error': repr(e)}; log(st, name, seed, 'ERROR', repr(e), traceback.format_exc()[-800:])
            log(st, name, 'seed', seed, {k: v for k, v in rec['seeds'][seed].items() if k != 'train_loss'}, 'last loss', rec['seeds'][seed].get('train_loss', [None])[-1])
        META['models'][name] = rec
    json.dump(META, open(os.path.join(sd, 'final_meta.json'), 'w'), indent=1, default=str)
    log(st, 'DONE')

for st in SETS:
    try:
        run_set(st)
    except Exception as e:
        log(st, 'FATAL', repr(e), traceback.format_exc()[-2000:])
