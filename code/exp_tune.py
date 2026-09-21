"""Stage 3 tuning (STAGE2_DESIGN_FROZEN_v1.1 §8 + C1-C3). Reads ONLY train_01 of the requested sets.
Usage: python exp_tune.py --sets set_01,set_03 --device cuda:0 --out /kaggle/working/tune"""
import os, sys, re, json, time, glob, hashlib, argparse, subprocess, traceback, zipfile
import numpy as np, torch
from sklearn.metrics import average_precision_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feats, models

ap = argparse.ArgumentParser()
ap.add_argument('--sets', required=True); ap.add_argument('--device', default='cuda:0')
ap.add_argument('--out', default='/kaggle/working/tune'); ap.add_argument('--lgb_threads', type=int, default=2)
args = ap.parse_args()
DEV = args.device; OUT = args.out; os.makedirs(OUT, exist_ok=True)
SETS = args.sets.split(',')
EPOCH_CAP, PATIENCE, BS = 20, 3, 1024
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
    with zipfile.ZipFile(ZIP) as z:
        names = [n for n in z.namelist() if n.startswith(f'can-train-and-test/{st}/train_01/') and n.endswith('.csv')]
        assert names and all('/train_01/' in n for n in names)
        for n in names:
            dest = os.path.join(DATA, n)
            if not os.path.exists(dest):
                z.extract(n, DATA)
    files = sorted(glob.glob(os.path.join(DATA, 'can-train-and-test', st, 'train_01', '*.csv')))
    for p in files:
        rel = p.split('can-train-and-test/')[1]; hh = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(8 << 20), b''): hh.update(b)
        assert (os.path.getsize(p), hh.hexdigest()) == H[rel], 'hash mismatch ' + rel
    return files

def fam(p): return re.sub(r'-\d+\.csv$', '', os.path.basename(p))
def idx(p): return int(re.search(r'-(\d+)\.csv$', p).group(1))

KEYS = ['frame', 'node', 'nmask', 'src', 'dst', 'glob', 'y']
def build_features(files):
    F = {}
    for p in files:
        d = feats.windows_for_file(p, 32)
        d['struct'] = feats.structural_features(d['src'], d['dst'], d['nmask'])
        F[p] = d
    return F

def cat(F, plist, stride64):
    out = {k: [] for k in KEYS + ['struct']}
    for p in plist:
        d = F[p]; sel = (d['starts'] % 64 == 0) if stride64 else slice(None)
        for k in out: out[k].append(d[k][sel])
    return {k: np.concatenate(v) for k, v in out.items()}

def flat_features(D, with_struct):
    m = D['nmask'][..., None]; x = D['node'].astype(np.float32); cnt = m.sum(1).clip(1)
    mean = (x * m).sum(1) / cnt; std = np.sqrt(((x - mean[:, None]) ** 2 * m).sum(1) / cnt)
    mn = np.where(m, x, np.inf).min(1); mx = np.where(m, x, -np.inf).max(1)
    X = [mean, std, mn, mx, D['glob']]
    if with_struct: X.append(D['struct'])
    return np.concatenate(X, 1).astype(np.float32)

NF, NN, NG = len(feats.FRAME_NAMES), len(feats.NODE_NAMES), len(feats.GLOBAL_NAMES)
def make(name, h, drop):
    if name in ('GraphSAGE', 'GraphSAGE_rewired'): return models.GraphSAGE(NN, h, NG, drop)
    if name == 'DeepSets': return models.DeepSets(NN, h, NG, drop)
    if name == 'GRU': return models.GRUNet(NF, h, NG, drop)
def matched_hidden(name, h_sage):
    if name in ('GraphSAGE', 'GraphSAGE_rewired'): return h_sage
    target = models.nparams(make('GraphSAGE', h_sage, 0.0))
    return min(range(4, 513), key=lambda h: abs(models.nparams(make(name, h, 0.0)) - target))

NEURAL_GRID = [dict(lr=lr, h_sage=h, dropout=dr) for lr in (1e-3, 3e-4) for h in (32, 64) for dr in (0.0, 0.2)]
LGB_GRID = [dict(num_leaves=nl, learning_rate=lr, min_child_samples=mc) for nl in (31, 63) for lr in (0.05, 0.1) for mc in (20, 100)]

def to_gpu(D, norm):
    T = {}
    T['frame'] = ((torch.from_numpy(D['frame'].astype(np.float32)).to(DEV) - norm['fm']) / norm['fs']).half()
    nm = torch.from_numpy(D['nmask']).to(DEV)
    T['node'] = (((torch.from_numpy(D['node'].astype(np.float32)).to(DEV) - norm['nm']) / norm['ns']) * nm.unsqueeze(-1)).half()
    T['nmask'] = nm
    T['glob'] = ((torch.from_numpy(D['glob']).to(DEV) - norm['gm']) / norm['gs'])
    T['src'] = torch.from_numpy(D['src']).to(DEV); T['dst'] = torch.from_numpy(D['dst']).to(DEV)
    T['y'] = torch.from_numpy(D['y'].astype(np.float32)).to(DEV)
    return T

def norm_stats(D):
    f = D['frame'].astype(np.float32).reshape(-1, NF); msk = D['nmask'].reshape(-1)
    n = D['node'].astype(np.float32).reshape(-1, NN)[msk]
    T = lambda a: torch.tensor(a, dtype=torch.float32, device=DEV)
    return {'fm': T(f.mean(0)), 'fs': T(f.std(0) + 1e-6), 'nm': T(n.mean(0)), 'ns': T(n.std(0) + 1e-6), 'gm': T(D['glob'].mean(0)), 'gs': T(D['glob'].std(0) + 1e-6)}

def batch(T, ix, rewire, gen):
    b = {'frame': T['frame'][ix].float(), 'node': T['node'][ix].float(), 'nmask': T['nmask'][ix], 'glob': T['glob'][ix]}
    dst = T['dst'][ix]
    if rewire: dst = models.rewire_dst(dst, gen)
    b['adj'] = models.build_adj(T['src'][ix], dst, len(ix), DEV)
    return b

def score(m, T, rewire, seed=12345):
    m.eval(); g = torch.Generator(device=DEV); g.manual_seed(seed); out = []
    with torch.no_grad():
        for s in range(0, len(T['y']), 4096):
            ix = torch.arange(s, min(s + 4096, len(T['y'])), device=DEV)
            out.append(m(batch(T, ix, rewire, g)).float())
    return torch.cat(out).cpu().numpy()

def train_neural(name, cfg, Ttr, Tva, yva, seed=0):
    torch.manual_seed(seed); np.random.seed(seed)
    gen = torch.Generator(device=DEV); gen.manual_seed(seed)
    h = matched_hidden(name, cfg['h_sage']); m = make(name, h, cfg['dropout']).to(DEV)
    opt = torch.optim.AdamW(m.parameters(), lr=cfg['lr'])
    pos = float(Ttr['y'].sum()); neg = len(Ttr['y']) - pos
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(neg / max(pos, 1.0), device=DEV))
    rew = name == 'GraphSAGE_rewired'; hist = []; best = (-1, None, None, None); bad = 0
    n = len(Ttr['y'])
    for ep in range(EPOCH_CAP):
        m.train(); t = time.time()
        perm = torch.randperm(n, device=DEV, generator=gen)
        for s in range(0, n, BS):
            ix = perm[s:s + BS]
            loss = lossf(m(batch(Ttr, ix, rew, gen)), Ttr['y'][ix]); opt.zero_grad(); loss.backward(); opt.step()
        sc = score(m, Tva, rew)
        apv = float(average_precision_score(yva, sc)) if yva.sum() > 0 else float('nan')
        pr = 1 / (1 + np.exp(-np.clip(sc, -30, 30)))
        bce = float(log_loss(yva, pr, labels=[0, 1]))
        hist.append({'epoch': ep + 1, 'val_ap': round(apv, 6), 'val_bce': round(bce, 6), 's': round(time.time() - t, 1)})
        if apv > best[0]:
            best = (apv, ep + 1, bce, sc.astype(np.float32)); bad = 0
        else:
            bad += 1
            if bad >= PATIENCE: break
    return {'hidden': h, 'params': models.nparams(m), 'best_ap': best[0], 'best_epoch': best[1], 'best_bce': best[2], 'history': hist}, best[3]

def train_lgb(cfg, Xtr, ytr, Xva, yva):
    import lightgbm as lgb
    pos = ytr.sum(); neg = len(ytr) - pos
    clf = lgb.LGBMClassifier(n_estimators=1000, scale_pos_weight=neg / max(pos, 1), n_jobs=args.lgb_threads, verbose=-1, random_state=0, metric='average_precision', **cfg)
    clf.fit(Xtr, ytr, eval_set=[(Xva, yva)], callbacks=[lgb.early_stopping(50, first_metric_only=True, verbose=False)])
    bi = clf.best_iteration_ or 1000
    sc = clf.predict_proba(Xva, num_iteration=bi)[:, 1]
    return {'best_ap': float(average_precision_score(yva, sc)), 'best_epoch': int(bi), 'best_bce': float(log_loss(yva, sc, labels=[0, 1]))}, sc.astype(np.float32)

def select(runs, grid, size_key):
    # runs[ci][fold] -> result dict ; tie-break per v1.1 C3
    rows = []
    for ci, cfg in enumerate(grid):
        r = [runs[ci][f] for f in (1, 2)]
        if any(x is None for x in r): continue
        rows.append(dict(ci=ci, ap=np.mean([x['best_ap'] for x in r]), bce=np.mean([x['best_bce'] for x in r]),
                         ep=np.mean([x['best_epoch'] for x in r]), size=cfg[size_key], lr=cfg.get('lr', cfg.get('learning_rate'))))
    best_ap = max(r['ap'] for r in rows)
    tied = [r for r in rows if r['ap'] >= best_ap - 0.001]
    tied.sort(key=lambda r: (r['bce'], r['ep'], r['size'], r['lr']))
    ch = tied[0]
    return {'config_index': ch['ci'], 'config': grid[ch['ci']], 'mean_val_ap': ch['ap'], 'mean_val_bce': ch['bce'],
            'final_epochs': max(1, int(round(ch['ep']))), 'n_tied_within_0.001': len(tied), 'all': rows}

def run_set(st):
    sd = os.path.join(OUT, st); os.makedirs(sd, exist_ok=True)
    if os.path.exists(os.path.join(sd, 'selection.json')):
        log(st, 'already done'); return
    t0 = time.time(); files = extract_train(st); log(st, 'train files', len(files), 'extract+verify s', round(time.time() - t0, 1))
    lo = min(idx(p) for p in files)
    folds = {1: ([p for p in files if idx(p) == lo], [p for p in files if idx(p) != lo]),
             2: ([p for p in files if idx(p) != lo], [p for p in files if idx(p) == lo])}
    t0 = time.time(); F = build_features(files); log(st, 'features s', round(time.time() - t0, 1))
    FD = {f: (cat(F, folds[f][0], False), cat(F, folds[f][1], True)) for f in (1, 2)}
    meta = {'set': st, 'folds': {f: {'train': [os.path.basename(p) for p in folds[f][0]], 'val': [os.path.basename(p) for p in folds[f][1]]} for f in (1, 2)},
            'windows': {f: {'train': int(len(FD[f][0]['y'])), 'train_pos': int(FD[f][0]['y'].sum()), 'val': int(len(FD[f][1]['y'])), 'val_pos': int(FD[f][1]['y'].sum())} for f in (1, 2)}}
    json.dump(meta, open(os.path.join(sd, 'meta.json'), 'w'), indent=1)
    SEL = {}; OOF = {}
    # Rule: best single base feature (56) by mean validation AP over folds
    Xb = {f: (flat_features(FD[f][0], False), flat_features(FD[f][1], False)) for f in (1, 2)}
    best = None
    for j in range(Xb[1][1].shape[1]):
        for sg in (1, -1):
            a = np.mean([average_precision_score(FD[f][1]['y'], sg * Xb[f][1][:, j]) for f in (1, 2)])
            if best is None or a > best[0]: best = (a, j, sg)
    SEL['Rule'] = {'feature_index': best[1], 'sign': best[2], 'mean_val_ap': best[0]}
    OOF['Rule'] = {f: (best[2] * Xb[f][1][:, best[1]]).astype(np.float32) for f in (1, 2)}
    log(st, 'Rule', SEL['Rule'])
    # LightGBM and LightGBM+S
    for name, ws in (('LightGBM', False), ('LightGBM_S', True)):
        X = {f: (flat_features(FD[f][0], ws), flat_features(FD[f][1], ws)) for f in (1, 2)}
        runs = {ci: {} for ci in range(len(LGB_GRID))}; sc_store = {ci: {} for ci in range(len(LGB_GRID))}
        for ci, cfg in enumerate(LGB_GRID):
            for f in (1, 2):
                t = time.time()
                try:
                    r, sc = train_lgb(cfg, X[f][0], FD[f][0]['y'], X[f][1], FD[f][1]['y']); runs[ci][f] = r; sc_store[ci][f] = sc
                except Exception as e:
                    runs[ci][f] = None; log(st, name, ci, f, 'ERROR', repr(e))
                log(st, name, 'cfg', ci, 'fold', f, runs[ci][f] and {k: runs[ci][f][k] for k in ('best_ap', 'best_epoch')}, round(time.time() - t, 1), 's')
        SEL[name] = select(runs, LGB_GRID, 'num_leaves'); SEL[name]['n_features'] = int(X[1][0].shape[1])
        OOF[name] = sc_store[SEL[name]['config_index']]
        json.dump({'runs': runs}, open(os.path.join(sd, f'runs_{name}.json'), 'w'), default=str)
        log(st, name, 'selected', SEL[name]['config'], SEL[name]['mean_val_ap'])
    # Neural models
    for f in (1, 2):
        norm = norm_stats(FD[f][0])
        FD[f] = (to_gpu(FD[f][0], norm), to_gpu(FD[f][1], norm), FD[f][1]['y'])
    for name in ('DeepSets', 'GRU', 'GraphSAGE'):
        runs = {ci: {} for ci in range(len(NEURAL_GRID))}; sc_store = {ci: {} for ci in range(len(NEURAL_GRID))}
        for ci, cfg in enumerate(NEURAL_GRID):
            for f in (1, 2):
                t = time.time()
                try:
                    r, sc = train_neural(name, cfg, FD[f][0], FD[f][1], FD[f][2]); runs[ci][f] = r; sc_store[ci][f] = sc
                except Exception as e:
                    runs[ci][f] = None; log(st, name, ci, f, 'ERROR', repr(e), traceback.format_exc()[-800:])
                log(st, name, 'cfg', ci, 'fold', f, runs[ci][f] and {k: runs[ci][f][k] for k in ('best_ap', 'best_epoch', 'params')}, round(time.time() - t, 1), 's')
        SEL[name] = select(runs, NEURAL_GRID, 'h_sage')
        SEL[name]['hidden'] = matched_hidden(name, SEL[name]['config']['h_sage'])
        OOF[name] = sc_store[SEL[name]['config_index']]
        json.dump({'runs': runs}, open(os.path.join(sd, f'runs_{name}.json'), 'w'), default=str)
        log(st, name, 'selected', SEL[name]['config'], SEL[name]['mean_val_ap'], 'epochs', SEL[name]['final_epochs'])
    # GraphSAGE_rewired: GraphSAGE's selected configuration, both folds (for out-of-fold scores), no selection
    cfg = SEL['GraphSAGE']['config']; runs = {}; OOF['GraphSAGE_rewired'] = {}
    for f in (1, 2):
        try:
            r, sc = train_neural('GraphSAGE_rewired', cfg, FD[f][0], FD[f][1], FD[f][2]); runs[f] = r; OOF['GraphSAGE_rewired'][f] = sc
        except Exception as e:
            runs[f] = {'best_ap': None, 'error': repr(e)}; OOF['GraphSAGE_rewired'][f] = np.zeros(len(FD[f][2]), np.float32)
            log(st, 'GraphSAGE_rewired', f, 'ERROR', repr(e), traceback.format_exc()[-800:])
        log(st, 'GraphSAGE_rewired fold', f, runs[f].get('best_ap'))
    SEL['GraphSAGE_rewired'] = {'config': cfg, 'hidden': SEL['GraphSAGE']['hidden'], 'final_epochs': SEL['GraphSAGE']['final_epochs'],
                                'fold_best_ap': {f: runs[f]['best_ap'] for f in (1, 2)}, 'note': 'uses GraphSAGE selection (v1.0 §7)'}
    json.dump({'runs': runs}, open(os.path.join(sd, 'runs_GraphSAGE_rewired.json'), 'w'), default=str)
    np.savez_compressed(os.path.join(sd, 'oof_scores.npz'), **{f'{k}_f{f}': v[f] for k, v in OOF.items() for f in (1, 2)},
                        **{f'y_f{f}': (FD[f][2]).astype(np.int8) for f in (1, 2)})
    json.dump(SEL, open(os.path.join(sd, 'selection.json'), 'w'), indent=1, default=str)
    log(st, 'DONE')

for st in SETS:
    try:
        run_set(st)
    except Exception as e:
        log(st, 'FATAL', repr(e), traceback.format_exc()[-2000:])
