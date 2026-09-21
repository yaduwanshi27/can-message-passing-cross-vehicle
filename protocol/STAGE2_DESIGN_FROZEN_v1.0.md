# STAGE 2 — FROZEN EXPERIMENTAL DESIGN v1.0

**Study:** CAN intrusion detection under vehicle and attack distribution shift — does relational message passing add anything?
**Frozen:** 2026-09-17 · **Decision authority:** user (D1–D9 decided in chat, 2026-09-17) · **Written by:** Claude (worker)
**Basis:** `DATASET_INTEGRITY_STAGE1B.md`, `STAGE1C_EVIDENCE_AND_STAGE2_DESIGN_DRAFT.md` (Part I evidence; Part II adopted except where overridden below), D1–D9, and implementation fixes F1–F5.

**Change control:** this document is not edited. Any change requires a new version (v1.1, …) with a dated reason. Implementation inconvenience is not a reason. Pilot results may change *runtime parameters in §10 only*, never cells, models, features, labels, metrics or statistics.

---

## 1. Dataset
- can-train-and-test **v1**, DTU Data, DOI 10.11583/DTU.24805533.v1, CC BY 4.0. Archive MD5 `bd6509d670c0a0009cb3ecab34111bcd` (VERIFIED against the local copy). Not v1.5 (the Bitbucket v1.5 extension adds further test subsets/attacks that are not used).
- Every run verifies all 236 CSVs by SHA-256 (digest `15111c4aad65c438c0cce8da77ff904944ab822ac06f3c91163bdd4e5680064b` over sorted `path,size,sha256` lines) and aborts on mismatch.

## 2. Research question and hypotheses
**RQ.** Under vehicle and attack distribution shift, does relational message passing provide generalisation beyond flat, permutation-invariant and sequential alternatives when message identity is controlled?
- **H1 (primary):** PR-AUC(GraphSAGE) − PR-AUC(DeepSets) on the B cells.
- **H1a (structure):** PR-AUC(GraphSAGE) − PR-AUC(GraphSAGE-rewired) on the B cells.
- **H2 (temporal control):** PR-AUC(GraphSAGE) − PR-AUC(GRU) on the B cells.
- All outcomes (better / practically equivalent / worse / inconclusive) are reportable.

## 3. Cells (D1)
| Role | Cells |
|---|---|
| **B — Primary** (unknown vehicle, known attack) | set_01/test_02, set_02/test_02, set_03/test_02, set_04/test_02 |
| C — Secondary (known vehicle, unknown attack) | test_03 of all four sets |
| D — Diagnostic (unknown vehicle, unknown attack) | test_04 of set_02, set_03, set_04 |
| A — Reference (known vehicle, known attack) | test_01 of all four sets |
| Excluded from all vehicle-shift claims | set_01/test_04 (Traverse by fingerprint; byte-identical to set_02/test_01) — dataset-integrity section only |

- B results are always reported per cell and by stratum: **same-manufacturer** (set_01: Impala→Silverado) and **cross-manufacturer** (set_02, set_03, set_04).
- Each set is trained and evaluated independently; no training data is pooled across sets.

## 4. Windows and labels (D5)
- Frames in recorded file order; timestamps never re-sorted; windows never cross files.
- W = 64 frames. **Training stride 32; validation and test stride 64** (non-overlapping; trailing partial window dropped).
- **Label:** positive if the window contains ≥1 `attack=1` frame.
- **Recording assignment precedes window generation** (F1).

## 5. Identity control
- The arbitration-ID value is **never** an input to any model (no raw value, embedding, hash, one-hot, lookup statistic or per-ID training baseline). It is used only to group frames into nodes and to define transitions.
- Automated test: randomly permuting ID labels inside a window leaves every model's output unchanged (tolerance 1e-6).

## 6. Features
**Frame features** (GRU input; computed inside the window only): payload length (bytes); time since previous frame (any ID); time since previous frame of the same ID (missing flag if none); Hamming distance to previous payload of the same ID (missing flag); fraction of changed bytes vs previous same-ID payload; byte entropy of payload; same-ID-as-previous-frame indicator; ID-first-occurrence-in-window indicator.

**Node features** (DeepSets / GraphSAGE; one node per distinct ID in window): frame count / W; first and last position / W; mean, min, max same-ID inter-arrival (missing flag if count = 1); mean and max payload length; payload-length-changes indicator; mean Hamming distance and mean changed-byte fraction between consecutive same-ID payloads; mean payload entropy.

**Edges:** directed ID(i)→ID(i+1) for consecutive frames; weight = count/63; self-loops kept.

**Global window features** (appended identically to every model's pooled representation and given to LightGBM and the rule): window duration; distinct IDs; distinct transitions; frames per second.

**LightGBM input:** mean, std, min, max of every node feature over the window's nodes + global features.

**Normalisation:** statistics from the training windows of the current fold/set only.

**D4 ablation (mandatory):** all payload-length-derived features removed (frame: payload length; node: mean/max payload length, change indicator), all models, reported per attack family.

## 7. Models (fixed; no additions)
| Model | Definition | Role |
|---|---|---|
| Rule | single global/aggregated feature with a threshold, both chosen on validation PR-AUC | floor |
| LightGBM | gradient-boosted trees on §6 input | flat baseline |
| GRU | 1-layer GRU over 64 frame vectors → last + mean hidden state → 2-layer MLP | temporal control (D2) |
| DeepSets | φ: 2-layer MLP per node → sum ⊕ mean ⊕ max → ρ: 2-layer MLP | no-relation control |
| GraphSAGE | 2 SAGEConv layers (mean aggregation, edge-weighted, directed) → same pooling and ρ | primary model |
| GraphSAGE-rewired | identical to GraphSAGE, but each window's edges replaced by degree-preserving rewiring (in- and out-degree preserved); new rewiring each epoch, fixed seed at evaluation | structure control |

- Neural models are capacity-matched: parameter counts within ±10% of GraphSAGE, same optimiser (AdamW), schedule, early-stopping rule and epoch cap.
- **Rewiring validity (F3):** the pilot measures the mean fraction of edges changed per window. If < 0.50, the rewired control uses a directed configuration-model randomisation with the same degree sequences instead. The chosen method and measured change fraction are reported.
- GraphSAGE-rewired uses GraphSAGE's selected hyper-parameters (no separate tuning).

## 8. Training, validation, thresholds (D6, D7, F1)
- **Loss:** class-weighted BCE (weight = negative/positive training windows). LightGBM: `scale_pos_weight` likewise.
- **2-fold recording-level cross-fitting inside train_01:** fold 1 trains on recordings with the lower index of each family (1 or 3) and validates on the higher (2 or 4); fold 2 swaps. Attack-free and accessory recordings follow the same rule.
- **Tuning** (overrides the 12-configuration draft to bound compute; equal for all models): grid of 8 configurations per neural model (learning rate {1e-3, 3e-4} × hidden {h_small, h_large} × dropout {0, 0.2}) and 8 for LightGBM (num_leaves {31, 63} × learning rate {0.05, 0.1} × min_child_samples {20, 100}); selected by mean validation PR-AUC over both folds; epoch count = mean best epoch.
- **Final model:** retrained on all train_01 recordings with the selected configuration and epoch count.
- **Thresholds:** derived from the pooled out-of-fold validation scores only: (i) max-F1 threshold for Macro-F1; (ii) FA/h thresholds as the highest threshold whose out-of-fold false-positive count ≤ floor(r × validation hours) for r ∈ {1, 5}.
- **No target-domain calibration** of any kind.
- **Seeds:** 5 for final models (initialisation, batch order, rewiring). Tuning uses seed 0.

## 9. Metrics and statistics (D3, D8, F2)
- **Primary:** window-level PR-AUC (average precision) per cell, reported with the cell's prevalence (= chance-level PR-AUC).
- **Secondary:** Macro-F1 at the validation threshold; recall at 1 and 5 FA/h with achieved test FA/h and the maximum false-positive count each operating point allows (descriptive, not used for inference).
- **Per family:** PR-AUC per attack token for tokens with ≥50 positive windows in the cell.
- **Uncertainty:** 2,000-resample bootstrap over test recordings (files), stratified by attack token; for each resample, metric averaged over the 5 seeds.
- **Paired differences** computed on identical windows. B-summary = mean of the four per-cell differences, bootstrap stratified by cell (B cells share no recordings, VERIFIED).
- **Decision rule (D3):** superiority / inferiority if the 95% CI excludes 0; **practical equivalence only if the 90% CI lies within ±0.02 PR-AUC** (margin prespecified); otherwise inconclusive. Holm correction over per-cell secondary tests. Wording in the paper: "a PR-AUC difference of ±0.02 was prespecified as the practical-equivalence margin; equivalence was concluded only when the 90% interval of the paired difference lay within this margin."
- Any aggregate spanning several cells counts each SHA-256 once.
- Sensitivity analyses (re-use the §8 selected configurations; no re-tuning; 5 seeds; B cells only): W = 32 and 128; negative windows inside the attack span removed from the negative set (evaluation-only, no retraining). The D4 ablation likewise re-uses selected configurations and is evaluated on all cells.

## 10. Compute and execution (D9, F4)
- Execution platform: cloud GPU notebook (Colab or equivalent free/paid notebook service); data downloaded from DTU inside the notebook and hash-verified.
- **Pilot (engineering only, uses train_01 of set_01, both folds; no test cell is scored):** measures feature-extraction time, time/epoch per model, memory, rewiring change fraction, convergence, checkpoint/resume. Output: runtime table and projected total GPU-hours.
- Runs are checkpointed per (set, model, config, fold/seed) and resumable after a disconnect.
- Parameters the pilot may change: batch size, epoch cap, data-loader workers, precision (fp32/fp16), and — only if the projected budget is infeasible — the tuning grid reduced **equally for all models**.

## 11. Leakage and artefact checklist (automated)
1. SHA-256 verification (§1). 2. Per set, no SHA-256 in both train_01 and any test cell. 3. ID-permutation invariance (§5). 4. Normalisation from training windows only. 5. Windows never cross files; folds split by file. 6. Test cells are read only by the final evaluation script. 7. Prevalence, recordings and hours reported for every cell.
