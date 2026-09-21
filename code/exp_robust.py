"""Stage 7 — pre-registered robustness analyses (STAGE2_DESIGN_FROZEN_v1.0 §6 D4, §9 sensitivity). Frozen k03 selections, 5 seeds,
NO retuning, NO threshold selection, NO target calibration. Cannot alter RESULTS_FROZEN_v1.0.
  --mode d4   : W=64; payload-length-derived features (frame plen; node plen_mean, plen_max, plen_changes) removed for ALL models
                (implemented by setting them to 0 before normalisation = removal: constant inputs carry no information), all cells.
  --mode w32  : W=32  (train stride 16, eval stride 32), B cells.
  --mode w128 : W=128 (train stride 64, eval stride 128), B cells.
Usage: python exp_robust.py --mode d4 --sets set_01,set_03 --device cuda:0"""
import os, sys, re, json, time, glob, hashlib, argparse, traceback, zipfile
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import featsW as feats, modelsW as models

ap = argparse.ArgumentParser()
ap.add_argument('--mode', required=True, choices=['d4', 'w32', 'w128']); ap.add_argument('--sets', required=True)
ap.add_argument('--device', default='cuda:0'); ap.add_argument('--out', default='/kaggle/working/robust')
ap.add_argument('--seeds', default='0,1,2,3,4'); ap.add_argument('--lgb_threads', type=int, default=2)
args = ap.parse_args()
MODE = args.mode; DEV = args.device; SETS = args.sets.split(','); SEEDS = [int(s) for s in args.seeds.split(',')]
W = {'d4': 64, 'w32': 32, 'w128': 128}[MODE]; TRAIN_STRIDE = W // 2; EVAL_STRIDE = W; BS = 1024
feats.set_W(W); models.set_W(W)
OUT = os.path.join(args.out, MODE); os.makedirs(OUT, exist_ok=True)
ZIP = glob.glob('/kaggle/input/**/can-train-and-test-v1.zip', recursive=True)[0]
HASHES = glob.glob('/kaggle/input/**/file_hashes_sha256.csv', recursive=True)[0]
DATA = '/kaggle/temp/data'
EXCLUDED = {('set_01', 'test_04')}
MODELS = ('Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired')
D4_FRAME = [feats.FRAME_NAMES.index('plen')]
D4_NODE = [feats.NODE_NAMES.index(n) for n in ('plen_mean', 'plen_max', 'plen_changes')]
CONST_STD = 1.5e-6; EVAL_REWIRE_SEED = 12345
LOG = open(os.path.join(OUT, f'log_{"_".join(SETS)}.txt'), 'a')
def log(*a):
    s = time.strftime('%H:%M:%S ') + f'[{MODE}] ' + ' '.join(str(x) for x in a); print(s, flush=True); LOG.write(s + '\n'); LOG.flush()

H = {}
for line in open(HASHES).read().strip().split('\n')[1:]:
    rel, size, sha = line.split(','); H[rel] = (int(size), sha)
def fam(n): return re.sub(r'-\d+\.csv$', '', os.path.basename(n))
def sha_of(p):
    hh = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): hh.update(b)
    return hh.hexdigest()
def get_file(z, n):
    p = os.path.join(DATA, n)
    if not os.path.exists(p): z.extract(n, DATA)
    rel = n.split('can-train-and-test/')[1]
    assert (os.path.getsize(p), sha_of(p)) == H[rel], 'hash mismatch ' + rel
    return p, rel

NF, NN, NG = len(feats.FRAME_NAMES), len(feats.NODE_NAMES), len(feats.GLOBAL_NAMES)
def make(name, h, drop):
    if name in ('GraphSAGE', 'GraphSAGE_rewired'): return models.GraphSAGE(NN, h, NG, drop)
    if name == 'DeepSets': return models.DeepSets(NN, h, NG, drop)
    if name == 'GRU': return models.GRUNet(NF, h, NG, drop)

def windows(p, stride):
    d = feats.windows_for_file(p, stride)
    if d is None: return None
    if MODE == 'd4':
        fr = d['frame'].copy(); fr[..., D4_FRAME] = 0; d['frame'] = fr
        nd = d['node'].copy(); nd[..., D4_NODE] = 0; d['node'] = nd
    d['struct'] = feats.structural_features(d['src'], d['dst'], d['nmask'])
    return d

def flat_features(D, with_struct):   # identical to exp_tune / exp_final / exp_eval
    m = D['nmask'][..., None]; x = D['node'].astype(np.float32); cnt = m.sum(1).clip(1)
    mean = (x * m).sum(1) / cnt; std = np.sqrt(((x - mean[:, None]) ** 2 * m).sum(1) / cnt)
    mn = np.where(m, x, np.inf).min(1); mx = np.where(m, x, -np.inf).max(1)
    X = [mean, std, mn, mx, D['glob']]
    if with_struct: X.append(D['struct'])
    return np.concatenate(X, 1).astype(np.float32)

def norm_stats(D):
    f = D['frame'].astype(np.float32).reshape(-1, NF); msk = D['nmask'].reshape(-1)
    n = D['node'].astype(np.float32).reshape(-1, NN)[msk]
    return {'fm': f.mean(0), 'fs': f.std(0) + 1e-6, 'nm': n.mean(0), 'ns': n.std(0) + 1e-6, 'gm': D['glob'].mean(0), 'gs': D['glob'].std(0) + 1e-6}

def to_gpu(D, N, with_y):
    """float32; features constant in training set to 0 (as k05 v2). Returns tensors + input diagnostics."""
    T = lambda a: torch.tensor(a, dtype=torch.float32, device=DEV)
    fm, fs, nm_, ns, gm, gs = T(N['fm']), T(N['fs']), T(N['nm']), T(N['ns']), T(N['gm']), T(N['gs'])
    kf, kn, kg = (fs > CONST_STD).float(), (ns > CONST_STD).float(), (gs > CONST_STD).float()
    msk = torch.from_numpy(D['nmask']).to(DEV)
    out = {'frame': ((torch.from_numpy(D['frame'].astype(np.float32)).to(DEV) - fm) / fs) * kf,
           'node': (((torch.from_numpy(D['node'].astype(np.float32)).to(DEV) - nm_) / ns) * msk.unsqueeze(-1)) * kn,
           'glob': ((torch.from_numpy(D['glob']).to(DEV) - gm) / gs) * kg, 'nmask': msk,
           'src': torch.from_numpy(D['src']).to(DEV), 'dst': torch.from_numpy(D['dst']).to(DEV), 'n': len(D['y'])}
    if with_y: out['y'] = torch.from_numpy(D['y'].astype(np.float32)).to(DEV)
    return out

def batch(T, ix, rewire, gen):
    b = {'frame': T['frame'][ix], 'node': T['node'][ix], 'nmask': T['nmask'][ix], 'glob': T['glob'][ix]}
    dst = T['dst'][ix]
    if rewire: dst = models.rewire_dst(dst, gen)
    b['adj'] = models.build_adj(T['src'][ix], dst, len(ix), DEV)
    return b

def score_neural(m, T, rewire):
    m.eval(); g = torch.Generator(device=DEV); g.manual_seed(EVAL_REWIRE_SEED); out = []
    with torch.no_grad():
        for s in range(0, T['n'], 2048):
            ix = torch.arange(s, min(s + 2048, T['n']), device=DEV)
            out.append(m(batch(T, ix, rewire, g)).float())
    return torch.cat(out).cpu().numpy().astype(np.float32)

KEYS = ['frame', 'node', 'nmask', 'src', 'dst', 'glob', 'y', 'struct']

def run_set(st):
    sd = os.path.join(OUT, st); os.makedirs(sd, exist_ok=True)
    if os.path.exists(os.path.join(sd, 'DONE')): log(st, 'already done'); return
    SEL = json.load(open(glob.glob(f'/kaggle/input/**/tune/{st}/selection.json', recursive=True)[0]))
    t0 = time.time()
    with zipfile.ZipFile(ZIP) as z:
        allnames = z.namelist()
        trn = sorted(n for n in allnames if n.startswith(f'can-train-and-test/{st}/train_01/') and n.endswith('.csv'))
        F = [windows(get_file(z, n)[0], TRAIN_STRIDE) for n in trn]
    F = [d for d in F if d is not None]
    D = {k: np.concatenate([d[k] for d in F]) for k in KEYS}; del F
    log(st, 'train files', len(trn), 'windows', len(D['y']), 'pos', int(D['y'].sum()), 'W', W, 'stride', TRAIN_STRIDE, 's', round(time.time() - t0, 1))
    N = norm_stats(D)
    const = {'frame': [feats.FRAME_NAMES[i] for i in np.flatnonzero(N['fs'] <= CONST_STD)], 'node': [feats.NODE_NAMES[i] for i in np.flatnonzero(N['ns'] <= CONST_STD)],
             'glob': [feats.GLOBAL_NAMES[i] for i in np.flatnonzero(N['gs'] <= CONST_STD)]}
    log(st, 'training-constant features (zeroed):', const)
    meta = {'mode': MODE, 'W': W, 'train_stride': TRAIN_STRIDE, 'eval_stride': EVAL_STRIDE, 'train_windows': int(len(D['y'])), 'train_pos': int(D['y'].sum()),
            'constant_in_training': const, 'models': {}}
    # ---- train (frozen k03 selections, no tuning) ----
    import lightgbm as lgb
    LGB = {}
    for name, ws in (('LightGBM', False), ('LightGBM_S', True)):
        X = flat_features(D, ws); y = D['y']; pos = y.sum(); neg = len(y) - pos; LGB[name] = []
        for seed in SEEDS:
            clf = lgb.LGBMClassifier(n_estimators=SEL[name]['final_epochs'], scale_pos_weight=neg / max(pos, 1), n_jobs=args.lgb_threads, verbose=-1,
                                     random_state=seed, **SEL[name]['config'])
            clf.fit(X, y); LGB[name].append(clf.booster_)
            clf.booster_.save_model(os.path.join(sd, f'{name}_seed{seed}.txt'))
        meta['models'][name] = {'config': SEL[name]['config'], 'n_estimators': SEL[name]['final_epochs']}
        log(st, name, 'trained 5 seeds'); del X
    T = to_gpu(D, N, True); n = T['n']; pos = float(T['y'].sum()); neg = n - pos; NNET = {}
    for name in ('DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired'):
        sel = SEL[name]; cfg = sel['config']; h = sel['hidden']; E = sel['final_epochs']; NNET[name] = []
        for seed in SEEDS:
            torch.manual_seed(seed); np.random.seed(seed)
            gen = torch.Generator(device=DEV); gen.manual_seed(seed)
            m = make(name, h, cfg['dropout']).to(DEV); opt = torch.optim.AdamW(m.parameters(), lr=cfg['lr'])
            lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(neg / max(pos, 1.0), device=DEV)); rew = name == 'GraphSAGE_rewired'; t = time.time()
            for ep in range(E):
                m.train(); perm = torch.randperm(n, device=DEV, generator=gen); tot = 0.0
                for s in range(0, n, BS):
                    ix = perm[s:s + BS]
                    loss = lossf(m(batch(T, ix, rew, gen)), T['y'][ix]); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(ix)
            assert np.isfinite(tot), f'non-finite training loss {st} {name} {seed}'
            torch.save(m.state_dict(), os.path.join(sd, f'{name}_seed{seed}.pt')); m.eval(); NNET[name].append(m)
            log(st, name, 'seed', seed, 'epochs', E, 'params', models.nparams(m), 'last loss', round(tot / n, 6), 's', round(time.time() - t, 1))
        meta['models'][name] = {'config': cfg, 'hidden': h, 'epochs': E, 'params': models.nparams(NNET[name][0])}
    del T; torch.cuda.empty_cache(); del D
    json.dump(meta, open(os.path.join(sd, 'train_meta.json'), 'w'), indent=1, default=str)
    # ---- evaluate ----
    train_sha = {H[r][1] for r in H if r.startswith(f'{st}/train_01/')}
    with zipfile.ZipFile(ZIP) as z:
        allnames = z.namelist()
        cells = sorted({n.split('/')[2] for n in allnames if n.startswith(f'can-train-and-test/{st}/test_') and n.endswith('.csv')})
        for cell in cells:
            short = cell[:7]
            if (st, short) in EXCLUDED: continue
            if MODE != 'd4' and short != 'test_02': continue
            names = sorted(n for n in allnames if n.startswith(f'can-train-and-test/{st}/{cell}/') and n.endswith('.csv'))
            parts = {k: [] for k in KEYS + ['nattack', 'starts']}; fid = []; finfo = []
            for i, nm in enumerate(names):
                p, rel = get_file(z, nm); assert H[rel][1] not in train_sha, 'LEAKAGE ' + rel
                d = windows(p, EVAL_STRIDE)
                for k in parts: parts[k].append(d[k])
                fid.append(np.full(len(d['y']), i, np.int16))
                finfo.append({'file': os.path.basename(nm), 'relative_path': rel, 'sha256': H[rel][1], 'token': fam(nm), 'windows': int(len(d['y'])),
                              'pos': int(d['y'].sum()), 'hours': float(d['t1'].max() - d['t0'].min()) / 3600.0})
            Dt = {k: np.concatenate(v) for k, v in parts.items()}; fid = np.concatenate(fid)
            S = {}
            Xb = flat_features(Dt, False); Xs = flat_features(Dt, True)
            S['Rule'] = (SEL['Rule']['sign'] * Xb[:, SEL['Rule']['feature_index']])[None].astype(np.float32)
            S['LightGBM'] = np.stack([b.predict(Xb) for b in LGB['LightGBM']]).astype(np.float32)
            S['LightGBM_S'] = np.stack([b.predict(Xs) for b in LGB['LightGBM_S']]).astype(np.float32)
            Tt = to_gpu(Dt, N, False)
            for name, lst in NNET.items(): S[name] = np.stack([score_neural(m, Tt, name == 'GraphSAGE_rewired') for m in lst])
            del Tt; torch.cuda.empty_cache()
            for m in MODELS: assert np.isfinite(S[m]).all(), f'non-finite scores {st} {cell} {m}'
            np.savez_compressed(os.path.join(sd, f'{short}_scores.npz'), y=Dt['y'].astype(np.int8), file_id=fid, nattack=Dt['nattack'], starts=Dt['starts'],
                                **{f'score_{m}': S[m] for m in MODELS})
            json.dump({'set': st, 'cell': cell, 'mode': MODE, 'W': W, 'files': finfo, 'windows': int(len(Dt['y'])), 'pos': int(Dt['y'].sum()),
                       'prevalence': float(Dt['y'].mean()), 'hours': float(sum(f['hours'] for f in finfo))},
                      open(os.path.join(sd, f'{short}_meta.json'), 'w'), indent=1)
            log(st, cell, 'windows', len(Dt['y']), 'pos', int(Dt['y'].sum()))
    open(os.path.join(sd, 'DONE'), 'w').write('ok'); log(st, 'DONE')

for st in SETS:
    try:
        run_set(st)
    except Exception as e:
        log(st, 'FATAL', repr(e), traceback.format_exc()[-2000:])
