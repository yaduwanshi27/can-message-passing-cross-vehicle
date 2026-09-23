import torch, torch.nn as nn, numpy as np, time
W = 64

def mlp(i, h, o, drop):
    return nn.Sequential(nn.Linear(i, h), nn.ReLU(), nn.Dropout(drop), nn.Linear(h, o))

class Head(nn.Module):
    def __init__(self, h, g, drop):
        super().__init__(); self.rho = mlp(3 * h + g, h, 1, drop)
    def forward(self, H, mask, glob):
        m = mask.unsqueeze(-1).float()
        s = (H * m).sum(1); mean = s / m.sum(1).clamp(min=1)
        mx = H.masked_fill(m == 0, -1e4).max(1).values
        return self.rho(torch.cat([s, mean, mx, glob], 1)).squeeze(-1)

class DeepSets(nn.Module):
    def __init__(self, f, h, g, drop=0.0):
        super().__init__()
        self.phi = nn.Sequential(nn.Linear(f, h), nn.ReLU(), nn.Dropout(drop), nn.Linear(h, h), nn.ReLU())
        self.head = Head(h, g, drop)
    def forward(self, b):
        return self.head(self.phi(b['node']), b['nmask'], b['glob'])

class SAGELayer(nn.Module):
    def __init__(self, i, o):
        super().__init__(); self.self_lin = nn.Linear(i, o); self.nei_lin = nn.Linear(i, o, bias=False)
    def forward(self, H, A):
        # A[b, src, dst] = weight; aggregate incoming neighbours of each dst node (weighted mean)
        agg = torch.bmm(A.transpose(1, 2), H)
        deg = A.sum(1).unsqueeze(-1)
        agg = agg / deg.clamp(min=1e-9)
        return self.self_lin(H) + self.nei_lin(agg)

class GraphSAGE(nn.Module):
    def __init__(self, f, h, g, drop=0.0):
        super().__init__()
        self.l1 = SAGELayer(f, h); self.l2 = SAGELayer(h, h); self.drop = nn.Dropout(drop)
        self.head = Head(h, g, drop)
    def forward(self, b):
        A = b['adj']; m = b['nmask'].unsqueeze(-1).float()
        H = torch.relu(self.l1(b['node'], A)) * m
        H = torch.relu(self.l2(self.drop(H), A)) * m
        return self.head(H, b['nmask'], b['glob'])

class GRUNet(nn.Module):
    def __init__(self, f, h, g, drop=0.0):
        super().__init__()
        self.gru = nn.GRU(f, h, batch_first=True); self.out = mlp(2 * h + g, h, 1, drop)
    def forward(self, b):
        O, hn = self.gru(b['frame'])
        return self.out(torch.cat([hn[-1], O.mean(1), b['glob']], 1)).squeeze(-1)

def nparams(m):
    return sum(p.numel() for p in m.parameters())

def build_adj(src, dst, B, device):
    A = torch.zeros(B, W, W, device=device)
    bi = torch.arange(B, device=device).unsqueeze(1).expand_as(src)
    A.index_put_((bi.reshape(-1), src.reshape(-1).long(), dst.reshape(-1).long()), torch.full((src.numel(),), 1.0 / 63, device=device), accumulate=True)
    return A

def rewire_dst(dst, gen):
    # degree-preserving directed rewiring: permute destination endpoints among a window's 63 edges
    # (every source keeps its out-degree, every destination keeps its in-degree, multiplicities included)
    r = torch.rand(dst.shape, generator=gen, device=dst.device)
    perm = r.argsort(1)
    return torch.gather(dst, 1, perm)

def edge_change_fraction(src, dst, dst2):
    # fraction of the 63 directed edges (as a multiset per window) not present in the original
    B = src.shape[0]
    k1 = (src.long() * 64 + dst.long()).sort(1).values
    k2 = (src.long() * 64 + dst2.long()).sort(1).values
    fr = []
    for i in range(B):
        a, ca = torch.unique(k1[i], return_counts=True); b2, cb = torch.unique(k2[i], return_counts=True)
        common = 0
        d = dict(zip(a.tolist(), ca.tolist()))
        for kk, cc in zip(b2.tolist(), cb.tolist()):
            common += min(cc, d.get(kk, 0))
        fr.append(1 - common / 63.0)
    return float(np.mean(fr))


# ---------------- v1.2 extension: attention-based message passing (STAGE2_DESIGN_ADDENDUM_v1.2_GAT) ----------------
class GATLayer(nn.Module):
    """Same layer form as SAGELayer: out = Theta_s h_v + sum_u alpha_uv Theta_n h_u, with multi-head attention over the observed
    incoming transitions u->v:  alpha_uv = softmax_u( LeakyReLU_0.2(a_src.Theta_n h_u + a_dst.Theta_n h_v) + log A_uv ).
    With a = 0 this reduces exactly to SAGELayer's transition-weighted mean (log A_uv keeps the multiplicities).
    Nodes with no incoming transition receive a zero neighbour message (as SAGELayer)."""
    def __init__(self, i, o, heads=4):
        super().__init__()
        assert o % heads == 0
        self.k = heads; self.d = o // heads
        self.self_lin = nn.Linear(i, o); self.nei_lin = nn.Linear(i, o, bias=False)
        self.a_src = nn.Parameter(torch.zeros(heads, self.d)); self.a_dst = nn.Parameter(torch.zeros(heads, self.d))
        nn.init.xavier_uniform_(self.a_src); nn.init.xavier_uniform_(self.a_dst)
    def forward(self, H, A):
        B, N, _ = H.shape
        Wh = self.nei_lin(H).view(B, N, self.k, self.d)                      # (B,N,K,d)
        es = (Wh * self.a_src).sum(-1); ed = (Wh * self.a_dst).sum(-1)       # (B,N,K)
        logits = torch.nn.functional.leaky_relu(es.unsqueeze(2) + ed.unsqueeze(1), 0.2)   # (B,u,v,K)
        edge = (A > 0).unsqueeze(-1)
        logits = logits + torch.log(A.clamp(min=1e-12)).unsqueeze(-1)
        logits = logits.masked_fill(~edge, -1e9)
        alpha = torch.softmax(logits, dim=1) * edge.float()                  # softmax over sources u; zero where no edge
        msg = torch.einsum('buvk,bukd->bvkd', alpha, Wh).reshape(B, N, self.k * self.d)
        return self.self_lin(H) + msg

class GAT(nn.Module):
    def __init__(self, f, h, g, drop=0.0, heads=4):
        super().__init__()
        self.l1 = GATLayer(f, h, heads); self.l2 = GATLayer(h, h, heads); self.drop = nn.Dropout(drop)
        self.head = Head(h, g, drop)
    def forward(self, b):
        A = b['adj']; m = b['nmask'].unsqueeze(-1).float()
        H = torch.relu(self.l1(b['node'], A)) * m
        H = torch.relu(self.l2(self.drop(H), A)) * m
        return self.head(H, b['nmask'], b['glob'])
