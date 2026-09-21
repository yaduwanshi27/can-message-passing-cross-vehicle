import os, sys, json, time, glob, hashlib, subprocess, traceback, math, re
import numpy as np, torch
from sklearn.metrics import average_precision_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feats, models
from set01_train_hashes import SET01_TRAIN

OUT = '/kaggle/working'
REPORT = {'stage': 'pilot', 'design': 'STAGE2_DESIGN_FROZEN_v1.0', 'note': 'engineering pilot: set_01/train_01 only, 2 recording-level folds, no test cell read', 'errors': []}
def save():
    json.dump(REPORT, open(OUT + '/pilot_report.json', 'w'), indent=1, default=str)
def log(k, v):
    REPORT[k] = v; print(k, json.dumps(v, default=str)[:2000], flush=True); save()
def stage(name, fn):
    t = time.time()
    try:
        r = fn(); log('time_' + name + '_s', round(time.time() - t, 1)); return r
    except Exception as e:
        REPORT['errors'].append({'stage': name, 'error': repr(e), 'trace': traceback.format_exc()[-3000:]}); save(); print('ERROR in', name, e, flush=True); return None

dev = 'cuda' if torch.cuda.is_available() else 'cpu'
env = {'device': dev, 'torch': torch.__version__}
if dev == 'cuda':
    env['gpu'] = torch.cuda.get_device_name(0); env['n_gpu'] = torch.cuda.device_count()
env['ram_GB'] = round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30, 1); env['cpus'] = os.cpu_count()
log('env', env)

ZIP = '/kaggle/temp/can.zip'; ROOT = '/kaggle/temp/data/can-train-and-test'
def get_data():
    os.makedirs('/kaggle/temp', exist_ok=True)
    if not os.path.exists(ZIP) or os.path.getsize(ZIP) != 1507455719:
        subprocess.run(['wget', '-q', '-O', ZIP, 'https://ndownloader.figshare.com/files/43632393'], check=True)
    h = hashlib.md5()
    with open(ZIP, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    assert h.hexdigest() == 'bd6509d670c0a0009cb3ecab34111bcd', 'zip md5 mismatch'
    # extract ONLY set_01/train_01 (test cells are never extracted in the pilot)
    subprocess.run(['unzip', '-q', '-o', ZIP, 'can-train-and-test/set_01/train_01/*', '-d', '/kaggle/temp/data'], check=True)
    extracted = sorted(glob.glob(ROOT + '/**/*.csv', recursive=True))
    assert all('/train_01/' in p for p in extracted), 'non-train file extracted'
    bad = []
    for rel, size, sha in SET01_TRAIN:
        p = ROOT + '/' + rel; hh = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(8 << 20), b''): hh.update(b)
        if hh.hexdigest() != sha or os.path.getsize(p) != int(size): bad.append(rel)
    assert not bad, 'hash mismatch ' + str(bad)
    return {'n_extracted': len(extracted), 'all_train_only': True, 'sha256_ok': True}
r = stage('data', get_data); log('data', r)
if r is None: sys.exit(0)

files = sorted(glob.glob(ROOT + '/set_01/train_01/*.csv'))
fam = lambda p: re.sub(r'-\d+\.csv$', '', os.path.basename(p))
idx = lambda p: int(re.search(r'-(\d+)\.csv$', p).group(1))
lo = min(idx(p) for p in files)
folds = {1: ([p for p in files if idx(p) == lo], [p for p in files if idx(p) != lo]),
         2: ([p for p in files if idx(p) != lo], [p for p in files if idx(p) == lo])}
log('folds', {k: {'train': [os.path.basename(p) for p in v[0]], 'val': [os.path.basename(p) for p in v[1]]} for k, v in folds.items()})

FEAT = {}
def extract():
    stats = {}
    for p in files:
        t = time.time(); d = feats.windows_for_file(p, 32); FEAT[p] = d
        stats[os.path.basename(p)] = {'windows_s32': int(len(d['y'])), 'pos_s32': int(d['y'].sum()), 's': round(time.time() - t, 1)}
    return stats
log('extraction', stage('extract', extract))

def idperm_test():
    p = files[0]; rng = np.random.default_rng(1); perm = rng.permutation(4096)
    a = FEAT[p]; b = feats.windows_for_file(p, 32, id_perm=perm)
    ok = np.array_equal(a['frame'], b['frame']) and np.array_equal(a['glob'], b['glob']) and np.array_equal(a['y'], b['y'])
    for w in rng.choice(len(a['y']), 500, replace=False):
        x = a['node'][w][a['nmask'][w]]; z = b['node'][w][b['nmask'][w]]
        ok &= np.array_equal(x[np.lexsort(x.T[::-1])], z[np.lexsort(z.T[::-1])])
    return bool(ok)
log('id_permutation_feature_invariance', stage('idperm', idperm_test))

def cat(plist, stride64):
    keys = ['frame', 'node', 'nmask', 'src', 'dst', 'glob', 'y']
    out = {k: [] for k in keys}
    for p in plist:
        d = FEAT[p]; sel = (d['starts'] % 64 == 0) if stride64 else slice(None)
        for k in keys: out[k].append(d[k][sel])
    return {k: np.concatenate(v) for k, v in out.items()}

def to_batch(D, ix, rewire=False, gen=None, norm=None):
    b = {}
    b['frame'] = torch.from_numpy(D['frame'][ix].astype(np.float32)).to(dev)
    b['node'] = torch.from_numpy(D['node'][ix].astype(np.float32)).to(dev)
    b['nmask'] = torch.from_numpy(D['nmask'][ix]).to(dev)
    b['glob'] = torch.from_numpy(D['glob'][ix]).to(dev)
    if norm is not None:
        b['frame'] = (b['frame'] - norm['fm']) / norm['fs']; b['node'] = (b['node'] - norm['nm']) / norm['ns'] * b['nmask'].unsqueeze(-1); b['glob'] = (b['glob'] - norm['gm']) / norm['gs']
    src = torch.from_numpy(D['src'][ix]).to(dev); dst = torch.from_numpy(D['dst'][ix]).to(dev)
    if rewire: dst = models.rewire_dst(dst, gen)
    b['adj'] = models.build_adj(src, dst, len(ix), dev)
    return b

def norm_stats(D):
    f = D['frame'].astype(np.float32).reshape(-1, D['frame'].shape[-1])
    m = D['nmask'].reshape(-1); n = D['node'].astype(np.float32).reshape(-1, D['node'].shape[-1])[m]
    T = lambda x: torch.tensor(x, dtype=torch.float32, device=dev)
    return {'fm': T(f.mean(0)), 'fs': T(f.std(0) + 1e-6), 'nm': T(n.mean(0)), 'ns': T(n.std(0) + 1e-6), 'gm': T(D['glob'].mean(0)), 'gs': T(D['glob'].std(0) + 1e-6)}

NF, NN, NG = len(feats.FRAME_NAMES), len(feats.NODE_NAMES), len(feats.GLOBAL_NAMES)
def make(name, h):
    if name == 'GraphSAGE' or name == 'GraphSAGE_rewired': return models.GraphSAGE(NN, h, NG)
    if name == 'DeepSets': return models.DeepSets(NN, h, NG)
    if name == 'GRU': return models.GRUNet(NF, h, NG)

def match_hidden():
    target = models.nparams(make('GraphSAGE', 64)); res = {'GraphSAGE': (64, target)}
    for nm in ['DeepSets', 'GRU']:
        best = min(range(8, 257), key=lambda h: abs(models.nparams(make(nm, h)) - target))
        res[nm] = (best, models.nparams(make(nm, best)))
    res['GraphSAGE_rewired'] = res['GraphSAGE']
    return {k: {'hidden': v[0], 'params': v[1], 'ratio_to_graphsage': round(v[1] / target, 3)} for k, v in res.items()}
HID = stage('capacity', match_hidden); log('capacity', HID)

EPOCHS = int(os.environ.get('PILOT_EPOCHS', '4')); BS = 1024
def train_eval(name, fold):
    torch.manual_seed(0); gen = torch.Generator(device=dev); gen.manual_seed(0)
    Dtr = cat(folds[fold][0], False); Dva = cat(folds[fold][1], True)
    norm = norm_stats(Dtr)
    m = make(name, HID[name]['hidden']).to(dev)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
    pos = Dtr['y'].sum(); neg = len(Dtr['y']) - pos
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(neg / max(pos, 1), device=dev))
    rew = name == 'GraphSAGE_rewired'
    rec = {'n_train_windows': int(len(Dtr['y'])), 'n_train_pos': int(pos), 'n_val_windows': int(len(Dva['y'])), 'n_val_pos': int(Dva['y'].sum()), 'epochs': []}
    if dev == 'cuda': torch.cuda.reset_peak_memory_stats()
    for ep in range(EPOCHS):
        m.train(); t = time.time(); perm = np.random.default_rng(ep).permutation(len(Dtr['y'])); tot = 0
        for s in range(0, len(perm), BS):
            ix = np.sort(perm[s:s + BS]); b = to_batch(Dtr, ix, rew, gen, norm)
            yb = torch.from_numpy(Dtr['y'][ix].astype(np.float32)).to(dev)
            loss = lossf(m(b), yb); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(ix)
        if dev == 'cuda': torch.cuda.synchronize()
        tr_s = time.time() - t
        m.eval(); t = time.time(); sc = []
        g2 = torch.Generator(device=dev); g2.manual_seed(12345)
        with torch.no_grad():
            for s in range(0, len(Dva['y']), 4096):
                ix = np.arange(s, min(s + 4096, len(Dva['y']))); sc.append(m(to_batch(Dva, ix, rew, g2, norm)).float().cpu().numpy())
        sc = np.concatenate(sc); ev_s = time.time() - t
        ap = average_precision_score(Dva['y'], sc) if Dva['y'].sum() > 0 else None
        rec['epochs'].append({'epoch': ep, 'train_loss': round(tot / len(perm), 5), 'train_s': round(tr_s, 1), 'val_score_s': round(ev_s, 1), 'val_ap_sanity': None if ap is None else round(float(ap), 4)})
        print(name, fold, rec['epochs'][-1], flush=True)
    if dev == 'cuda': rec['peak_gpu_mem_MB'] = round(torch.cuda.max_memory_allocated() / 2**20)
    ck = OUT + f'/ckpt_{name}_f{fold}.pt'; torch.save({'model': m.state_dict(), 'opt': opt.state_dict(), 'epoch': EPOCHS}, ck)
    m2 = make(name, HID[name]['hidden']).to(dev); st = torch.load(ck, map_location=dev); m2.load_state_dict(st['model'])
    rec['checkpoint_reload_identical'] = all(torch.equal(a, b) for a, b in zip(m.state_dict().values(), m2.state_dict().values()))
    os.remove(ck)
    return rec

RES = {}
for name in ['DeepSets', 'GraphSAGE', 'GraphSAGE_rewired', 'GRU']:
    for fold in [1, 2]:
        r = stage(f'train_{name}_f{fold}', lambda: train_eval(name, fold))
        RES[f'{name}_f{fold}'] = r; log('neural', RES)

def rewiring():
    D = cat(folds[1][1], True); ix = np.random.default_rng(0).choice(len(D['y']), 2000, replace=False)
    src = torch.from_numpy(D['src'][ix]).to(dev); dst = torch.from_numpy(D['dst'][ix]).to(dev)
    g = torch.Generator(device=dev); g.manual_seed(0)
    return {'mean_edge_change_fraction': round(models.edge_change_fraction(src, dst, models.rewire_dst(dst, g)), 4), 'n_windows': 2000,
            'rule': 'F3: if < 0.50 use directed configuration-model randomisation'}
log('rewiring', stage('rewiring', rewiring))

def lgbm_and_rule():
    import lightgbm as lgb
    def flat(D):
        m = D['nmask'][..., None]; x = D['node'].astype(np.float32); cnt = m.sum(1).clip(1)
        mean = (x * m).sum(1) / cnt; std = np.sqrt(((x - mean[:, None]) ** 2 * m).sum(1) / cnt)
        mn = np.where(m, x, np.inf).min(1); mx = np.where(m, x, -np.inf).max(1)
        return np.concatenate([mean, std, mn, mx, D['glob']], 1)
    out = {}
    for fold in [1, 2]:
        Dtr = cat(folds[fold][0], False); Dva = cat(folds[fold][1], True)
        Xtr, Xva = flat(Dtr), flat(Dva); pos = Dtr['y'].sum(); neg = len(Dtr['y']) - pos
        t = time.time()
        clf = lgb.LGBMClassifier(n_estimators=300, num_leaves=31, learning_rate=0.1, min_child_samples=20, scale_pos_weight=neg / max(pos, 1), verbose=-1)
        clf.fit(Xtr, Dtr['y']); fit_s = time.time() - t
        ap = average_precision_score(Dva['y'], clf.predict_proba(Xva)[:, 1])
        t = time.time(); best = (-1, None, None)
        for j in range(Xva.shape[1]):
            for sgn in (1, -1):
                a = average_precision_score(Dva['y'], sgn * Xva[:, j])
                if a > best[0]: best = (a, j, sgn)
        out[f'f{fold}'] = {'lgbm_fit_s': round(fit_s, 1), 'lgbm_val_ap_sanity': round(float(ap), 4), 'n_features': int(Xtr.shape[1]), 'rule_select_s': round(time.time() - t, 1), 'rule_feature_index': best[1], 'rule_sign': best[2], 'rule_val_ap_sanity': round(float(best[0]), 4)}
    return out
log('lgbm_rule', stage('lgbm_rule', lgbm_and_rule))

def projection():
    # windows at stride 32 per set's train_01 (from Stage 1C non-overlapping counts x2)
    tw = {'set_01': 332898, 'set_02': 541886, 'set_03': 375792, 'set_04': 296630}
    per_win = {}
    for name in ['DeepSets', 'GraphSAGE', 'GraphSAGE_rewired', 'GRU']:
        e = [RES[f'{name}_f{f}'] for f in (1, 2) if RES.get(f'{name}_f{f}')]
        if not e: continue
        s = np.mean([np.mean([x['train_s'] + x['val_score_s'] for x in r['epochs'][1:]] or [r['epochs'][0]['train_s']]) / r['n_train_windows'] for r in e])
        per_win[name] = s
    EPOCH_CAP = 20; hours = {}
    for name, s in per_win.items():
        full = sum(tw.values()) * s * EPOCH_CAP / 3600       # one full-train run on all 4 sets
        half = full / 2                                      # one fold run (half the recordings)
        tuning = 0 if name == 'GraphSAGE_rewired' else 8 * 2 * half
        finals = 5 * full; ablation = 5 * full
        sens = 2 * 5 * full                                  # W=32,128 (evaluation-set restriction not modelled)
        hours[name] = {'tuning_h': round(tuning, 2), 'finals_h': round(finals, 2), 'd4_ablation_h': round(ablation, 2), 'window_sensitivity_h': round(sens, 2), 'total_h': round(tuning + finals + ablation + sens, 2)}
    return {'assumed_epoch_cap': EPOCH_CAP, 'per_model': hours, 'total_gpu_hours_all_models': round(sum(v['total_h'] for v in hours.values()), 1)}
log('projection', stage('projection', projection))
log('status', 'DONE')
