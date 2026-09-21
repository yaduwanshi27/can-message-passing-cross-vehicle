"""Stage 5a final evaluation scoring (STAGE2_DESIGN_FROZEN_v1.0 §3,§9 + v1.1). THE ONLY SCRIPT THAT READS TEST CELLS.
Reads frozen k04 final models/thresholds/norm stats; writes per-window scores per cell. No fitting, no selection, no calibration.
Usage: python exp_eval.py --sets set_01,set_03 --device cuda:0"""
import os, sys, re, json, time, glob, hashlib, argparse, traceback, zipfile
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feats, models

ap = argparse.ArgumentParser()
ap.add_argument('--sets', required=True); ap.add_argument('--device', default='cuda:0')
ap.add_argument('--out', default='/kaggle/working/eval'); ap.add_argument('--seeds', default='0,1,2,3,4')
args = ap.parse_args()
DEV = args.device; OUT = args.out; os.makedirs(OUT, exist_ok=True)
SETS = args.sets.split(','); SEEDS = [int(s) for s in args.seeds.split(',')]
ZIP = glob.glob('/kaggle/input/**/can-train-and-test-v1.zip', recursive=True)[0]
HASHES = glob.glob('/kaggle/input/**/file_hashes_sha256.csv', recursive=True)[0]
DATA = f'/kaggle/temp/eval_{"_".join(SETS)}'
EXCLUDED = {('set_01', 'test_04')}   # v1.0 §3: Traverse by fingerprint, byte-identical to set_02/test_01; integrity section only
MODELS = ('Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired')
EVAL_REWIRE_SEED = 12345   # fixed rewiring seed at evaluation (v1.0 §7), same as used for tuning OOF scores
LOG = open(os.path.join(OUT, f'log_{"_".join(SETS)}.txt'), 'a')
def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a); print(s, flush=True); LOG.write(s + '\n'); LOG.flush()

H = {}
for line in open(HASHES).read().strip().split('\n')[1:]:
    rel, size, sha = line.split(','); H[rel] = (int(size), sha)
def fam(name): return re.sub(r'-\d+\.csv$', '', os.path.basename(name))

NF, NN, NG = len(feats.FRAME_NAMES), len(feats.NODE_NAMES), len(feats.GLOBAL_NAMES)
def make(name, h, drop):
    if name in ('GraphSAGE', 'GraphSAGE_rewired'): return models.GraphSAGE(NN, h, NG, drop)
    if name == 'DeepSets': return models.DeepSets(NN, h, NG, drop)
    if name == 'GRU': return models.GRUNet(NF, h, NG, drop)

def flat_features(D, with_struct):   # identical to exp_tune / exp_final
    m = D['nmask'][..., None]; x = D['node'].astype(np.float32); cnt = m.sum(1).clip(1)
    mean = (x * m).sum(1) / cnt; std = np.sqrt(((x - mean[:, None]) ** 2 * m).sum(1) / cnt)
    mn = np.where(m, x, np.inf).min(1); mx = np.where(m, x, -np.inf).max(1)
    X = [mean, std, mn, mx, D['glob']]
    if with_struct: X.append(D['struct'])
    return np.concatenate(X, 1).astype(np.float32)

CONST_STD = 1.5e-6   # norm stats store std + 1e-6; std <= 5e-7 means the feature was constant in the set's training windows
def to_gpu(D, N):
    """Same normalisation as k04 (training statistics only), but float32 (no fp16 overflow) and features that were CONSTANT in training
    are set to 0 = exactly the value every training window had (the model never learned a response to them). Decided before any test metric was seen."""
    T = lambda a: torch.tensor(a, dtype=torch.float32, device=DEV)
    fm, fs, nm_, ns, gm, gs = T(N['fm']), T(N['fs']), T(N['nm']), T(N['ns']), T(N['gm']), T(N['gs'])
    keepf, keepn, keepg = (fs > CONST_STD).float(), (ns > CONST_STD).float(), (gs > CONST_STD).float()
    out = {}; diag = {}
    msk = torch.from_numpy(D['nmask']).to(DEV)
    out['frame'] = ((torch.from_numpy(D['frame'].astype(np.float32)).to(DEV) - fm) / fs)
    out['node'] = (((torch.from_numpy(D['node'].astype(np.float32)).to(DEV) - nm_) / ns) * msk.unsqueeze(-1))
    out['glob'] = (torch.from_numpy(D['glob']).to(DEV) - gm) / gs
    for k, keep, names in (('frame', keepf, feats.FRAME_NAMES), ('node', keepn, feats.NODE_NAMES), ('glob', keepg, feats.GLOBAL_NAMES)):
        z = out[k].abs().reshape(-1, len(names))
        diag[k] = {nm: {'max_abs_z': float(z[:, j].max()), 'frac_abs_z_gt_100': float((z[:, j] > 100).float().mean()), 'constant_in_training_zeroed': bool(keep[j] == 0)}
                   for j, nm in enumerate(names)}
        out[k] = out[k] * keep
    out['nmask'] = msk
    out['src'] = torch.from_numpy(D['src']).to(DEV); out['dst'] = torch.from_numpy(D['dst']).to(DEV)
    out['n'] = len(D['y'])
    return out, diag

def batch(T, ix, rewire, gen):
    b = {'frame': T['frame'][ix].float(), 'node': T['node'][ix].float(), 'nmask': T['nmask'][ix], 'glob': T['glob'][ix]}
    dst = T['dst'][ix]
    if rewire: dst = models.rewire_dst(dst, gen)
    b['adj'] = models.build_adj(T['src'][ix], dst, len(ix), DEV)
    return b

def score_neural(m, T, rewire):
    m.eval(); g = torch.Generator(device=DEV); g.manual_seed(EVAL_REWIRE_SEED); out = []
    with torch.no_grad():
        for s in range(0, T['n'], 4096):
            ix = torch.arange(s, min(s + 4096, T['n']), device=DEV)
            out.append(m(batch(T, ix, rewire, g)).float())
    return torch.cat(out).cpu().numpy().astype(np.float32)

class Scorer:
    def __init__(self, st):
        import lightgbm as lgb
        fd = os.path.dirname(glob.glob(f'/kaggle/input/**/final/{st}/final_meta.json', recursive=True)[0])
        self.meta = json.load(open(os.path.join(fd, 'final_meta.json')))
        self.N = dict(np.load(os.path.join(fd, 'norm_stats.npz')))
        self.rule = self.meta['models']['Rule']
        self.lgb = {name: [lgb.Booster(model_file=os.path.join(fd, f'{name}_seed{s}.txt')) for s in SEEDS] for name in ('LightGBM', 'LightGBM_S')}
        self.nn = {}
        for name in ('DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired'):
            r = self.meta['models'][name]; lst = []
            for s in SEEDS:
                if 'error' in r['seeds'].get(str(s), r['seeds'].get(s, {})): raise RuntimeError(f'{st} {name} seed {s} failed in k04')
                m = make(name, r['hidden'], r['config']['dropout']).to(DEV)
                m.load_state_dict(torch.load(os.path.join(fd, f'{name}_seed{s}.pt'), map_location=DEV)); m.eval(); lst.append(m)
            self.nn[name] = lst
        self.fd = fd
    def score(self, D):
        S = {}
        Xb = flat_features(D, False); Xs = flat_features(D, True)
        S['Rule'] = (self.rule['sign'] * Xb[:, self.rule['feature_index']])[None].astype(np.float32)
        S['LightGBM'] = np.stack([b.predict(Xb) for b in self.lgb['LightGBM']]).astype(np.float32)      # probability scale, as OOF predict_proba
        S['LightGBM_S'] = np.stack([b.predict(Xs) for b in self.lgb['LightGBM_S']]).astype(np.float32)
        T, self.last_diag = to_gpu(D, self.N)
        for name, lst in self.nn.items():
            S[name] = np.stack([score_neural(m, T, name == 'GraphSAGE_rewired') for m in lst])          # logits, as OOF
        del T; torch.cuda.empty_cache()
        return S

KEYS = ['frame', 'node', 'nmask', 'src', 'dst', 'glob', 'y', 'struct', 'nattack', 'starts']
def file_windows(p, id_perm=None):
    d = feats.windows_for_file(p, 64, id_perm)
    d['struct'] = feats.structural_features(d['src'], d['dst'], d['nmask'])
    assert (d['starts'] % 64 == 0).all()
    return d

def sha_of(p):
    hh = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): hh.update(b)
    return hh.hexdigest()

def id_permutation_test(st, sc, p):
    """v1.0 §5 automated test: permuting ID labels leaves every model's output unchanged. Reports max |diff| (seed 0 / all seeds for trees)."""
    rng = np.random.default_rng(7); perm = rng.permutation(4096)
    d0 = file_windows(p); d1 = file_windows(p, perm)
    k = min(len(d0['y']), 3000)
    d0 = {kk: v[:k] for kk, v in d0.items() if kk in KEYS}; d1 = {kk: v[:k] for kk, v in d1.items() if kk in KEYS}
    s0, s1 = sc.score(d0), sc.score(d1)
    res = {m: float(np.abs(s0[m] - s1[m]).max()) for m in MODELS}
    res['ids_actually_permuted'] = True
    return res

def run_set(st):
    sd = os.path.join(OUT, st); os.makedirs(sd, exist_ok=True)
    sc = Scorer(st); log(st, 'loaded frozen k04 models from', sc.fd)
    const = {k: [n for n, v in zip(names, sc.N[key]) if v <= CONST_STD] for k, key, names in (('frame', 'fs', feats.FRAME_NAMES), ('node', 'ns', feats.NODE_NAMES), ('glob', 'gs', feats.GLOBAL_NAMES))}
    log(st, 'training-constant features (zeroed at test):', const)
    json.dump({'constant_in_training': const, 'fs': sc.N['fs'].tolist(), 'ns': sc.N['ns'].tolist(), 'gs': sc.N['gs'].tolist()}, open(os.path.join(sd, 'norm_diagnostics.json'), 'w'), indent=1)
    train_sha = {H[r][1] for r in H if r.startswith(f'{st}/train_01/')}
    with zipfile.ZipFile(ZIP) as z:
        allnames = z.namelist()
        cells = sorted({n.split('/')[2] for n in allnames if n.startswith(f'can-train-and-test/{st}/test_') and n.endswith('.csv')})
        for cell in cells:
            short = cell[:7]
            if (st, short) in EXCLUDED: log(st, cell, 'EXCLUDED by v1.0 §3 (not extracted, not scored)'); continue
            if os.path.exists(os.path.join(sd, f'{short}_scores.npz')): log(st, cell, 'already done'); continue
            names = sorted(n for n in allnames if n.startswith(f'can-train-and-test/{st}/{cell}/') and n.endswith('.csv'))
            t0 = time.time(); parts = {k: [] for k in KEYS}; fid = []; finfo = []
            for i, n in enumerate(names):
                z.extract(n, DATA); p = os.path.join(DATA, n); rel = n.split('can-train-and-test/')[1]
                sha = sha_of(p); assert (os.path.getsize(p), sha) == H[rel], 'hash mismatch ' + rel
                assert sha not in train_sha, 'LEAKAGE: test file identical to a train_01 file ' + rel
                if i == 0 and short == 'test_01':
                    pt = id_permutation_test(st, sc, p); log(st, 'ID-permutation test (max |score diff|)', pt)
                    json.dump(pt, open(os.path.join(sd, 'id_permutation_test.json'), 'w'), indent=1)
                d = file_windows(p); os.remove(p)
                for k in KEYS: parts[k].append(d[k])
                fid.append(np.full(len(d['y']), i, np.int16))
                finfo.append({'file': os.path.basename(n), 'relative_path': rel, 'sha256': sha, 'token': fam(n), 'windows': int(len(d['y'])),
                              'pos': int(d['y'].sum()), 'hours': float(d['t1'].max() - d['t0'].min()) / 3600.0})
            D = {k: np.concatenate(v) for k, v in parts.items()}; fid = np.concatenate(fid)
            tf = time.time() - t0; t0 = time.time()
            S = sc.score(D)
            for m in MODELS: assert np.isfinite(S[m]).all(), f'non-finite scores {st} {cell} {m}'
            cm_diag = sc.last_diag
            np.savez_compressed(os.path.join(sd, f'{short}_scores.npz'), y=D['y'].astype(np.int8), file_id=fid, nattack=D['nattack'], starts=D['starts'],
                                **{f'score_{m}': S[m] for m in MODELS})
            cm = {'set': st, 'cell': cell, 'files': finfo, 'windows': int(len(D['y'])), 'pos': int(D['y'].sum()),
                  'prevalence': float(D['y'].mean()), 'hours': float(sum(f['hours'] for f in finfo)), 'feature_s': round(tf, 1), 'score_s': round(time.time() - t0, 1),
                  'input_diagnostics': cm_diag, 'precision': 'float32; training-constant features zeroed'}
            json.dump(cm, open(os.path.join(sd, f'{short}_meta.json'), 'w'), indent=1)
            log(st, cell, {k: cm[k] for k in ('windows', 'pos', 'prevalence', 'hours', 'feature_s', 'score_s')})
    log(st, 'DONE')

for st in SETS:
    try:
        run_set(st)
    except Exception as e:
        log(st, 'FATAL', repr(e), traceback.format_exc()[-2000:])
