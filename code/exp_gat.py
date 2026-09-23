"""k09: v1.2 extension (STAGE2_DESIGN_ADDENDUM_v1.2_GAT). GAT and GAT-rewired: tuning (train_01 only), final models (5 seeds),
thresholds from out-of-fold scores, and scoring of the B cells (test_02) only. Identical rules to k03/k04/k05 v2.
Usage: python exp_gat.py --sets set_01,set_03 --device cuda:0 [--smoke]"""
import os, sys, re, json, time, glob, hashlib, argparse, traceback, zipfile, math
import numpy as np, torch
from sklearn.metrics import average_precision_score, log_loss, precision_recall_curve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feats, models

ap = argparse.ArgumentParser()
ap.add_argument('--sets', required=True); ap.add_argument('--device', default='cuda:0')
ap.add_argument('--out', default='/kaggle/working/gat'); ap.add_argument('--seeds', default='0,1,2,3,4')
ap.add_argument('--smoke', action='store_true', help='tiny run (2 configs, 1 epoch, 1 seed, 2 test files) to check the pipeline; writes to <out>_smoke')
args = ap.parse_args()
DEV = args.device; SETS = args.sets.split(','); SEEDS = [int(s) for s in args.seeds.split(',')]
OUT = args.out + ('_smoke' if args.smoke else ''); os.makedirs(OUT, exist_ok=True)
EPOCH_CAP, PATIENCE, BS = (1, 1, 1024) if args.smoke else (20, 3, 1024)
if args.smoke: SEEDS = SEEDS[:1]
ZIP = glob.glob('/kaggle/input/**/can-train-and-test-v1.zip', recursive=True)[0]
HASHES = glob.glob('/kaggle/input/**/file_hashes_sha256.csv', recursive=True)[0]
DATA = f'/kaggle/temp/gat_{"_".join(SETS)}'
EVAL_REWIRE_SEED = 12345; CONST_STD = 1.5e-6
MODELS = ('GAT', 'GAT_rewired')
LOG = open(os.path.join(OUT, f'log_{"_".join(SETS)}.txt'), 'a')
def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a); print(s, flush=True); LOG.write(s + '\n'); LOG.flush()

H = {}
for line in open(HASHES).read().strip().split('\n')[1:]:
    rel, size, sha = line.split(','); H[rel] = (int(size), sha)
def fam(n): return re.sub(r'-\d+\.csv$', '', os.path.basename(n))
def idx(p): return int(re.search(r'-(\d+)\.csv$', p).group(1))
def sha_of(p):
    hh = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): hh.update(b)
    return hh.hexdigest()

NF, NN, NG = len(feats.FRAME_NAMES), len(feats.NODE_NAMES), len(feats.GLOBAL_NAMES)
def make(name, h, drop):
    if name == 'GraphSAGE': return models.GraphSAGE(NN, h, NG, drop)
    return models.GAT(NN, h, NG, drop)
_MH = {}
def matched_hidden(h_sage):
    """GAT width (divisible by 4 heads) whose trainable-parameter count is closest to GraphSAGE's at that grid point; must be within 10%."""
    if h_sage in _MH: return _MH[h_sage]
    target = models.nparams(make('GraphSAGE', h_sage, 0.0))
    h = min(range(4, 513, 4), key=lambda x: abs(models.nparams(make('GAT', x, 0.0)) - target))
    assert abs(models.nparams(make('GAT', h, 0.0)) - target) <= 0.10 * target, 'parameter matching outside 10%'
    _MH[h_sage] = h; return h
NEURAL_GRID = [dict(lr=lr, h_sage=h, dropout=dr) for lr in (1e-3, 3e-4) for h in (32, 64) for dr in (0.0, 0.2)]
if args.smoke: NEURAL_GRID = NEURAL_GRID[:2]

def extract(z, names):
    out = []
    for n in names:
        p = os.path.join(DATA, n)
        if not os.path.exists(p): z.extract(n, DATA)
        rel = n.split('can-train-and-test/')[1]
        assert (os.path.getsize(p), sha_of(p)) == H[rel], 'hash mismatch ' + rel
        out.append(p)
    return out

KEYS = ['node', 'nmask', 'src', 'dst', 'glob', 'y']
def cat(F, plist, stride64):
    out = {k: [] for k in KEYS}
    for p in plist:
        d = F[p]; sel = (d['starts'] % 64 == 0) if stride64 else slice(None)
        for k in out: out[k].append(d[k][sel])
    return {k: np.concatenate(v) for k, v in out.items()}

def norm_stats(D, Fr=None):
    msk = D['nmask'].reshape(-1)
    n = D['node'].astype(np.float32).reshape(-1, NN)[msk]
    return {'fm': np.zeros(NF, np.float32), 'fs': np.ones(NF, np.float32), 'nm': n.mean(0), 'ns': n.std(0) + 1e-6, 'gm': D['glob'].mean(0), 'gs': D['glob'].std(0) + 1e-6}

def to_gpu(D, N, zero_const):
    """float32 throughout; at test (zero_const=True) features constant in training are set to 0, exactly as k05 v2."""
    T = lambda a: torch.tensor(a, dtype=torch.float32, device=DEV)
    fm, fs, nm_, ns, gm, gs = T(N['fm']), T(N['fs']), T(N['nm']), T(N['ns']), T(N['gm']), T(N['gs'])
    out = {}; msk = torch.from_numpy(D['nmask']).to(DEV)
    out['node'] = ((torch.from_numpy(D['node'].astype(np.float32)).to(DEV) - nm_) / ns) * msk.unsqueeze(-1)
    out['glob'] = (torch.from_numpy(D['glob'].astype(np.float32)).to(DEV) - gm) / gs
    if zero_const:
        out['node'] = out['node'] * (ns > CONST_STD).float(); out['glob'] = out['glob'] * (gs > CONST_STD).float()
    out['nmask'] = msk; out['src'] = torch.from_numpy(D['src']).to(DEV); out['dst'] = torch.from_numpy(D['dst']).to(DEV)
    out['y'] = torch.from_numpy(D['y'].astype(np.float32)).to(DEV); out['n'] = len(D['y'])
    return out

def batch(T, ix, rewire, gen):
    b = {'node': T['node'][ix], 'nmask': T['nmask'][ix], 'glob': T['glob'][ix]}
    dst = T['dst'][ix]
    if rewire: dst = models.rewire_dst(dst, gen)
    b['adj'] = models.build_adj(T['src'][ix], dst, len(ix), DEV)
    return b

def score(m, T, rewire):
    m.eval(); g = torch.Generator(device=DEV); g.manual_seed(EVAL_REWIRE_SEED); out = []
    with torch.no_grad():
        for s in range(0, T['n'], 2048):
            ix = torch.arange(s, min(s + 2048, T['n']), device=DEV)
            out.append(m(batch(T, ix, rewire, g)).float())
    return torch.cat(out).cpu().numpy().astype(np.float32)

def fit(name, cfg, h, Ttr, epochs, seed, Tva=None, yva=None):
    """Train; with Tva returns early-stopping history (tuning), else trains exactly `epochs` epochs (final)."""
    torch.manual_seed(seed); np.random.seed(seed)
    gen = torch.Generator(device=DEV); gen.manual_seed(seed)
    m = make('GAT', h, cfg['dropout']).to(DEV)
    opt = torch.optim.AdamW(m.parameters(), lr=cfg['lr'])
    pos = float(Ttr['y'].sum()); neg = Ttr['n'] - pos
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(neg / max(pos, 1.0), device=DEV))
    rew = name == 'GAT_rewired'; hist = []; best = (-1, None, None, None); bad = 0; losses = []
    for ep in range(epochs):
        m.train(); t = time.time(); perm = torch.randperm(Ttr['n'], device=DEV, generator=gen); tot = 0.0
        for s in range(0, Ttr['n'], BS):
            ix = perm[s:s + BS]
            loss = lossf(m(batch(Ttr, ix, rew, gen)), Ttr['y'][ix]); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(ix)
        losses.append(round(tot / Ttr['n'], 6))
        if Tva is None: continue
        sc = score(m, Tva, rew)
        apv = float(average_precision_score(yva, sc)) if yva.sum() > 0 else float('nan')
        bce = float(log_loss(yva, 1 / (1 + np.exp(-np.clip(sc, -30, 30))), labels=[0, 1]))
        hist.append({'epoch': ep + 1, 'val_ap': round(apv, 6), 'val_bce': round(bce, 6), 's': round(time.time() - t, 1)})
        if apv > best[0]: best = (apv, ep + 1, bce, sc); bad = 0
        else:
            bad += 1
            if bad >= PATIENCE: break
    if Tva is None: return m, losses
    return {'hidden': h, 'params': models.nparams(m), 'best_ap': best[0], 'best_epoch': best[1], 'best_bce': best[2], 'history': hist}, best[3]

def select(runs):
    rows = []
    for ci, cfg in enumerate(NEURAL_GRID):
        r = [runs[ci][f] for f in (1, 2)]
        if any(x is None for x in r): continue
        rows.append(dict(ci=ci, ap=np.mean([x['best_ap'] for x in r]), bce=np.mean([x['best_bce'] for x in r]),
                         ep=np.mean([x['best_epoch'] for x in r]), size=cfg['h_sage'], lr=cfg['lr']))
    best_ap = max(r['ap'] for r in rows); tied = [r for r in rows if r['ap'] >= best_ap - 0.001]
    tied.sort(key=lambda r: (r['bce'], r['ep'], r['size'], r['lr'])); ch = tied[0]
    return {'config_index': ch['ci'], 'config': NEURAL_GRID[ch['ci']], 'mean_val_ap': ch['ap'], 'mean_val_bce': ch['bce'],
            'final_epochs': max(1, int(round(ch['ep']))), 'n_tied_within_0.001': len(tied), 'all': rows}

def thresholds_from_oof(scores, y, hours):   # identical to k04
    neg = np.sort(scores[y == 0])[::-1]; pos = scores[y == 1]
    out = {'val_hours': hours, 'n_val_windows': int(len(y)), 'n_val_pos': int(y.sum())}
    p, r, t = precision_recall_curve(y, scores); f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12); i = int(np.argmax(f1))
    out['f1'] = {'threshold': float(t[i]), 'op': '>=', 'oof_f1': float(f1[i])}
    for rate in (1, 5):
        k = int(math.floor(rate * hours)); thr = float(neg[k]) if k < len(neg) else float(neg[-1]) - 1e-6
        out[f'fa{rate}'] = {'threshold': thr, 'op': '>', 'allowed_fp': k, 'oof_fp': int((neg > thr).sum()), 'oof_recall': float((pos > thr).mean()) if len(pos) else float('nan')}
    return out

def run_set(st):
    sd = os.path.join(OUT, st); os.makedirs(sd, exist_ok=True)
    if os.path.exists(os.path.join(sd, 'DONE')): log(st, 'already done'); return
    train_sha = {H[r][1] for r in H if r.startswith(f'{st}/train_01/')}
    with zipfile.ZipFile(ZIP) as z:
        allnames = z.namelist()
        tr_names = sorted(n for n in allnames if n.startswith(f'can-train-and-test/{st}/train_01/') and n.endswith('.csv'))
        t0 = time.time(); files = extract(z, tr_names); log(st, 'train files', len(files), 'extract+verify s', round(time.time() - t0, 1))
        # ---- folds: identical rule to k03; checked against k03 meta when available
        lo = min(idx(p) for p in files)
        folds = {1: ([p for p in files if idx(p) == lo], [p for p in files if idx(p) != lo]),
                 2: ([p for p in files if idx(p) != lo], [p for p in files if idx(p) == lo])}
        k03 = glob.glob(f'/kaggle/input/**/tune/{st}/meta.json', recursive=True)
        if k03:
            M = json.load(open(k03[0]))
            for f in (1, 2):
                assert sorted(M['folds'][str(f)]['train']) == sorted(os.path.basename(p) for p in folds[f][0]), 'fold mismatch vs k03'
            log(st, 'folds identical to k03')
        t0 = time.time(); F = {p: feats.windows_for_file(p, 32) for p in files}
        hours = sum(float(F[p]['t1'].max() - F[p]['t0'].min()) / 3600.0 for p in files)
        log(st, 'features s', round(time.time() - t0, 1), 'train hours', round(hours, 3))
        # ---- tuning (train_01 only)
        FD = {}
        for f in (1, 2):
            Dtr, Dva = cat(F, folds[f][0], False), cat(F, folds[f][1], True); N = norm_stats(Dtr)
            FD[f] = (to_gpu(Dtr, N, False), to_gpu(Dva, N, False), Dva['y'].astype(np.int8))
        runs = {ci: {} for ci in range(len(NEURAL_GRID))}; scs = {ci: {} for ci in range(len(NEURAL_GRID))}
        for ci, cfg in enumerate(NEURAL_GRID):
            h = matched_hidden(cfg['h_sage'])
            for f in (1, 2):
                t = time.time()
                try:
                    r, sc = fit('GAT', cfg, h, FD[f][0], EPOCH_CAP, 0, FD[f][1], FD[f][2]); runs[ci][f] = r; scs[ci][f] = sc
                except Exception as e:
                    runs[ci][f] = None; log(st, 'GAT', ci, f, 'ERROR', repr(e), traceback.format_exc()[-800:])
                log(st, 'GAT cfg', ci, 'fold', f, runs[ci][f] and {k: runs[ci][f][k] for k in ('best_ap', 'best_epoch', 'params')}, round(time.time() - t, 1), 's')
        SEL = {'GAT': select(runs)}; SEL['GAT']['hidden'] = matched_hidden(SEL['GAT']['config']['h_sage'])
        OOF = {'GAT': scs[SEL['GAT']['config_index']], 'GAT_rewired': {}}
        cfg = SEL['GAT']['config']; h = SEL['GAT']['hidden']; rr = {}
        for f in (1, 2):
            r, sc = fit('GAT_rewired', cfg, h, FD[f][0], EPOCH_CAP, 0, FD[f][1], FD[f][2]); rr[f] = r; OOF['GAT_rewired'][f] = sc
            log(st, 'GAT_rewired fold', f, r['best_ap'])
        SEL['GAT_rewired'] = {'config': cfg, 'hidden': h, 'final_epochs': SEL['GAT']['final_epochs'], 'fold_best_ap': {f: rr[f]['best_ap'] for f in (1, 2)},
                              'note': 'uses GAT selection (addendum v1.2 §3)'}
        json.dump({'runs': runs, 'runs_rewired': rr}, open(os.path.join(sd, 'tune_runs.json'), 'w'), default=str)
        json.dump(SEL, open(os.path.join(sd, 'selection.json'), 'w'), indent=1, default=str)
        log(st, 'GAT selected', SEL['GAT']['config'], 'hidden', h, 'val AP', round(SEL['GAT']['mean_val_ap'], 4), 'epochs', SEL['GAT']['final_epochs'], 'ties', SEL['GAT']['n_tied_within_0.001'])
        y_oof = np.concatenate([FD[1][2], FD[2][2]]).astype(np.int8)
        TH = {nm: thresholds_from_oof(np.concatenate([OOF[nm][1], OOF[nm][2]]).astype(np.float64), y_oof, hours) for nm in MODELS}
        json.dump(TH, open(os.path.join(sd, 'thresholds.json'), 'w'), indent=1)
        del FD; torch.cuda.empty_cache()
        # ---- final models (whole train_01)
        Dall = cat(F, files, False); N = norm_stats(Dall); np.savez(os.path.join(sd, 'norm_stats.npz'), **N)
        Tall = to_gpu(Dall, N, False); FIN = {}; META = {'set': st, 'train_windows': int(len(Dall['y'])), 'train_hours': hours, 'models': {}}
        for nm in MODELS:
            FIN[nm] = []; rec = {'config': cfg, 'hidden': h, 'epochs': SEL['GAT']['final_epochs'], 'seeds': {}}
            for seed in SEEDS:
                t = time.time(); m, losses = fit(nm, cfg, h, Tall, SEL['GAT']['final_epochs'], seed)
                torch.save(m.state_dict(), os.path.join(sd, f'{nm}_seed{seed}.pt')); m.eval(); FIN[nm].append(m)
                rec['seeds'][seed] = {'train_loss': losses, 'fit_s': round(time.time() - t, 1), 'params': models.nparams(m)}
                log(st, nm, 'seed', seed, 'params', models.nparams(m), 'last loss', losses[-1], 'fit s', rec['seeds'][seed]['fit_s'])
            META['models'][nm] = rec
        json.dump(META, open(os.path.join(sd, 'final_meta.json'), 'w'), indent=1, default=str)
        del Tall, Dall, F; torch.cuda.empty_cache()
        # ---- B cell (test_02) scoring: the only test data read by this script
        te_names = sorted(n for n in allnames if n.startswith(f'can-train-and-test/{st}/test_02_') and n.endswith('.csv'))
        if args.smoke: te_names = te_names[:2]
        parts = {k: [] for k in ['node', 'nmask', 'src', 'dst', 'glob', 'y', 'starts']}; fid = []; finfo = []
        for i, n in enumerate(te_names):
            p = extract(z, [n])[0]; rel = n.split('can-train-and-test/')[1]; sha = H[rel][1]
            assert sha not in train_sha, 'LEAKAGE: test file identical to a train_01 file ' + rel
            d = feats.windows_for_file(p, 64); os.remove(p); assert (d['starts'] % 64 == 0).all()
            for k in parts: parts[k].append(d[k])
            fid.append(np.full(len(d['y']), i, np.int16))
            finfo.append({'file': os.path.basename(n), 'relative_path': rel, 'sha256': sha, 'token': fam(n), 'windows': int(len(d['y'])),
                          'pos': int(d['y'].sum()), 'hours': float(d['t1'].max() - d['t0'].min()) / 3600.0})
        D = {k: np.concatenate(v) for k, v in parts.items()}; fid = np.concatenate(fid)
        T = to_gpu(D, N, True)
        S = {nm: np.stack([score(m, T, nm == 'GAT_rewired') for m in FIN[nm]]) for nm in MODELS}
        for nm in MODELS: assert np.isfinite(S[nm]).all(), f'non-finite scores {st} {nm}'
        # windows must be identical to k05's B-cell windows (same comparators)
        k05 = glob.glob(f'/kaggle/input/**/eval/{st}/test_02_scores.npz', recursive=True)
        if k05 and not args.smoke:
            Z = np.load(k05[0])
            assert np.array_equal(Z['y'], D['y'].astype(np.int8)) and np.array_equal(Z['file_id'], fid) and np.array_equal(Z['starts'], D['starts']), 'window mismatch vs k05'
            log(st, 'B-cell windows identical to k05')
        np.savez_compressed(os.path.join(sd, 'test_02_scores.npz'), y=D['y'].astype(np.int8), file_id=fid, starts=D['starts'], **{f'score_{nm}': S[nm] for nm in MODELS})
        json.dump({'set': st, 'cell': 'test_02', 'files': finfo, 'windows': int(len(D['y'])), 'pos': int(D['y'].sum()), 'prevalence': float(D['y'].mean()),
                   'hours': float(sum(f['hours'] for f in finfo))}, open(os.path.join(sd, 'test_02_meta.json'), 'w'), indent=1)
        if args.smoke: log(st, 'SMOKE: test_02 pipeline ran; score shapes', {nm: S[nm].shape for nm in MODELS}, '(no metric computed)')
        else: log(st, 'test_02 scored', {nm: round(float(np.mean([average_precision_score(D['y'], s) for s in S[nm]])), 4) for nm in MODELS})
    open(os.path.join(sd, 'DONE'), 'w').write('ok')
    log(st, 'DONE')

for st in SETS:
    try:
        run_set(st)
    except Exception as e:
        log(st, 'FATAL', repr(e), traceback.format_exc()[-2000:])
