import numpy as np, pandas as pd, re, os, time
W = 64

def set_W(w):
    """Window length (frames). Default 64 = frozen design; 32/128 only for the pre-registered window-sensitivity analysis."""
    global W
    W = int(w)
HEXV = np.full(256, 0, dtype=np.uint8)
for i, ch in enumerate('0123456789abcdef'):
    HEXV[ord(ch)] = i; HEXV[ord(ch.upper())] = i
POP = np.array([bin(i).count('1') for i in range(256)], dtype=np.uint8)

def slog(x):
    return np.sign(x) * np.log1p(np.abs(x))

def load_file(path):
    df = pd.read_csv(path, dtype={'arbitration_id': str, 'data_field': str, 'attack': np.int8}, keep_default_na=True)
    ts = df['timestamp'].to_numpy(np.float64)
    ids = df['arbitration_id'].str.rjust(3, '0').str[-3:]
    ib = np.frombuffer(''.join(ids.tolist()).encode('ascii'), dtype=np.uint8).reshape(-1, 3)
    idv = HEXV[ib].astype(np.int32)
    id_int = idv[:, 0] * 256 + idv[:, 1] * 16 + idv[:, 2]
    d = df['data_field'].fillna('')
    plen = (d.str.len().to_numpy() // 2).clip(0, 8).astype(np.int8)
    d16 = d.str[:16].str.ljust(16, '0')
    db = np.frombuffer(''.join(d16.tolist()).encode('ascii'), dtype=np.uint8).reshape(-1, 16)
    nib = HEXV[db]
    pay = (nib[:, 0::2] * 16 + nib[:, 1::2]).astype(np.uint8)
    posmask = np.arange(8)[None, :] < plen[:, None]
    pay = np.where(posmask, pay, 0).astype(np.uint8)
    y = df['attack'].to_numpy(np.int8)
    return ts, id_int, plen, pay, y

def per_frame_globals(ts, id_int, plen, pay):
    n = len(ts); idx = np.arange(n)
    order = np.lexsort((idx, id_int))
    prev = np.full(n, -1, dtype=np.int64)
    same = np.r_[False, id_int[order][1:] == id_int[order][:-1]]
    prev[order[same]] = order[np.flatnonzero(same) - 1]
    has = prev >= 0
    pp = np.where(has, prev, 0)
    dt_same = np.where(has, ts - ts[pp], 0.0)
    x = pay ^ pay[pp]
    ham = np.where(has, POP[x].sum(1), 0).astype(np.float32)
    maxlen = np.maximum(plen, plen[pp]).astype(np.float32)
    chg = np.where(has, (x != 0).sum(1) / np.maximum(maxlen, 1), 0).astype(np.float32)
    lenchg = np.where(has, plen != plen[pp], False)
    ent = np.zeros(n, dtype=np.float32)
    for s in range(0, n, 500000):
        b = pay[s:s + 500000]; L = plen[s:s + 500000].astype(np.int32)
        valid = np.arange(8)[None, :] < L[:, None]
        eq = (b[:, :, None] == b[:, None, :]) & valid[:, :, None] & valid[:, None, :]
        c = eq.sum(2).astype(np.float32)
        Lf = np.maximum(L, 1).astype(np.float32)[:, None]
        with np.errstate(divide='ignore', invalid='ignore'):
            term = np.where(valid, np.log2(np.where(c > 0, c, 1) / Lf), 0.0)
        ent[s:s + 500000] = -(term.sum(1) / Lf[:, 0])
    return prev, dt_same, ham, chg, ent, lenchg

FRAME_NAMES = ['plen', 'dt_prev_any', 'dt_same', 'no_prev_same_in_window', 'hamming', 'changed_frac', 'entropy', 'same_as_prev']
NODE_NAMES = ['count', 'first_pos', 'last_pos', 'ia_mean', 'ia_min', 'ia_max', 'ia_missing', 'plen_mean', 'plen_max', 'plen_changes', 'ham_mean', 'chg_mean', 'ent_mean']
GLOBAL_NAMES = ['duration', 'distinct_ids', 'distinct_transitions', 'fps']

def windows_for_file(path, stride, id_perm=None):
    ts, id_int, plen, pay, y = load_file(path)
    if id_perm is not None:
        id_int = id_perm[id_int]
    n = len(ts)
    if n < W:
        return None
    prev, dt_same_g, ham_g, chg_g, ent_g, lenchg_g = per_frame_globals(ts, id_int, plen, pay)
    starts = np.arange(0, n - W + 1, stride)
    nw = len(starts)
    I = starts[:, None] + np.arange(W)[None, :]
    ok = prev[I] >= starts[:, None]
    tsw = ts[I]
    dtp = np.diff(tsw, axis=1, prepend=tsw[:, :1])
    idw = id_int[I]
    fr = np.zeros((nw, W, len(FRAME_NAMES)), dtype=np.float32)
    fr[..., 0] = plen[I] / 8.0
    fr[..., 1] = slog(dtp * 1000)
    fr[..., 2] = np.where(ok, slog(dt_same_g[I] * 1000), 0)
    fr[..., 3] = ~ok
    fr[..., 4] = np.where(ok, ham_g[I] / 64.0, 0)
    fr[..., 5] = np.where(ok, chg_g[I], 0)
    fr[..., 6] = ent_g[I] / 3.0
    fr[:, 1:, 7] = idw[:, 1:] == idw[:, :-1]
    # nodes
    key = (np.arange(nw)[:, None] * 4096 + idw).ravel()
    uk, inv = np.unique(key, return_inverse=True)
    inv = inv.reshape(nw, W)
    win_of_node = uk // 4096
    node_first = np.searchsorted(win_of_node, np.arange(nw))
    local = inv - node_first[:, None]
    nn = np.bincount(win_of_node, minlength=nw)
    G = len(uk)
    fl = inv.ravel()
    pos = np.broadcast_to(np.arange(W), (nw, W)).ravel()
    okf = ok.ravel()
    def agg_sum(v, m=None):
        return np.bincount(fl, weights=(v if m is None else v * m), minlength=G)
    order = np.argsort(fl, kind='stable'); fs = fl[order]
    bnd = np.flatnonzero(np.r_[True, fs[1:] != fs[:-1]])
    def agg_min(v): return np.minimum.reduceat(v[order], bnd)
    def agg_max(v): return np.maximum.reduceat(v[order], bnd)
    cnt = np.bincount(fl, minlength=G).astype(np.float32)
    iak = np.where(okf, slog(dt_same_g[I].ravel() * 1000), np.nan)
    nia = agg_sum(okf.astype(np.float64))
    has_ia = nia > 0
    ia_mean = np.where(has_ia, agg_sum(np.nan_to_num(iak)) / np.maximum(nia, 1), 0)
    ia_min = np.where(has_ia, agg_min(np.where(okf, iak, np.inf)), 0)
    ia_max = np.where(has_ia, agg_max(np.where(okf, iak, -np.inf)), 0)
    pl = (plen[I].ravel()).astype(np.float64)
    nd = np.zeros((G, len(NODE_NAMES)), dtype=np.float32)
    nd[:, 0] = cnt / W
    nd[:, 1] = agg_min(pos.astype(np.float64)) / W
    nd[:, 2] = agg_max(pos.astype(np.float64)) / W
    nd[:, 3] = ia_mean; nd[:, 4] = ia_min; nd[:, 5] = ia_max
    nd[:, 6] = ~has_ia
    nd[:, 7] = agg_sum(pl) / cnt / 8.0
    nd[:, 8] = agg_max(pl) / 8.0
    nd[:, 9] = agg_max(pl) != agg_min(pl)
    nd[:, 10] = np.where(has_ia, agg_sum(ham_g[I].ravel().astype(np.float64), okf) / np.maximum(nia, 1) / 64.0, 0)
    nd[:, 11] = np.where(has_ia, agg_sum(chg_g[I].ravel().astype(np.float64), okf) / np.maximum(nia, 1), 0)
    nd[:, 12] = agg_sum(ent_g[I].ravel().astype(np.float64)) / cnt / 3.0
    node = np.zeros((nw, W, len(NODE_NAMES)), dtype=np.float32)
    node[win_of_node, np.arange(G) - node_first[win_of_node]] = nd
    # edges: local src/dst per transition
    src = local[:, :-1].astype(np.uint8); dst = local[:, 1:].astype(np.uint8)
    WW = W * W
    tr = np.unique((np.arange(nw)[:, None] * WW + local[:, :-1] * W + local[:, 1:]).ravel())
    ntr = np.bincount(tr // WW, minlength=nw)
    dur = tsw[:, -1] - tsw[:, 0]
    glob = np.stack([slog(dur * 1000), nn / W, ntr / float(W - 1), slog(W / np.maximum(dur, 1e-6))], 1).astype(np.float32)
    lab = (y[I].max(1) > 0).astype(np.int8)
    nattack = y[I].sum(1).astype(np.int16)
    return dict(frame=fr.astype(np.float16), node=node.astype(np.float16), nmask=(np.arange(W)[None, :] < nn[:, None]),
                src=src, dst=dst, glob=glob, y=lab, nattack=nattack, starts=starts.astype(np.int64), t0=tsw[:, 0], t1=tsw[:, -1])

STRUCT_NAMES = ['transition_entropy', 'unique_transition_ratio', 'self_loop_ratio', 'mean_out_degree',
                'max_out_degree', 'max_in_degree', 'degree_entropy', 'density']

def structural_features(src, dst, nmask):
    """Explicit structural/topological summaries of each window's directed transition multigraph.
    src, dst: (nw, 63) local node indices of consecutive frames; nmask: (nw, 64) valid nodes.
    Uses only ID-free graph structure (local node indices are arbitrary labels)."""
    nw, E = src.shape
    Wn = nmask.shape[1]; WW = Wn * Wn
    n = nmask.sum(1).astype(np.float64)
    s = src.astype(np.int64); d = dst.astype(np.int64)
    w = np.repeat(np.arange(nw), E)
    key = w * WW + (s * Wn + d).ravel()
    uk, cnt = np.unique(key, return_counts=True)
    uw = uk // WW; us = (uk % WW) // Wn; ud = (uk % WW) % Wn
    p = cnt / float(E)
    ent = np.bincount(uw, weights=-p * np.log2(p), minlength=nw) / np.log2(E)
    uniq = np.bincount(uw, minlength=nw) / float(E)
    selfr = (s == d).sum(1) / float(E)
    ns = us != ud
    outdeg = np.bincount(uw[ns] * Wn + us[ns], minlength=nw * Wn).reshape(nw, Wn).astype(np.float64)
    indeg = np.bincount(uw[ns] * Wn + ud[ns], minlength=nw * Wn).reshape(nw, Wn).astype(np.float64)
    e_ns = np.bincount(uw[ns], minlength=nw).astype(np.float64)
    mean_out = np.where(n > 0, e_ns / np.maximum(n, 1), 0)
    tot = outdeg + indeg; ts = tot.sum(1, keepdims=True)
    pd_ = np.where(ts > 0, tot / np.maximum(ts, 1), 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        h = -(np.where(pd_ > 0, pd_ * np.log2(np.where(pd_ > 0, pd_, 1)), 0)).sum(1)
    deg_ent = np.where(n > 1, h / np.log2(np.maximum(n, 2)), 0)
    dens = np.where(n > 1, e_ns / np.maximum(n * (n - 1), 1), 0)
    return np.stack([ent, uniq, selfr, mean_out, outdeg.max(1), indeg.max(1), deg_ent, dens], 1).astype(np.float32)
