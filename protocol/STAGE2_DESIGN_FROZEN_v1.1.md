# STAGE 2 — FROZEN EXPERIMENTAL DESIGN v1.1

**Supersedes:** v1.0 (2026-09-17). v1.0 remains the base document; **everything in v1.0 stays in force except the sections changed below.**
**Date:** 2026-09-18 · **Decision authority:** user (novelty-gate review: "GO — add structural-statistics LightGBM control") · **Written by:** Claude (worker)
**Evidence for the changes:** `NOVELTY_MEMO_STAGE2_5.md` (V2), engineering pilot `k01` (`RUN_LOG.md`).

**Change control:** no GPU tuning has been run under v1.0; no test cell has been extracted or scored. Every change below is therefore made before any selection or result exists.

---

## Change C1 — Structural-statistics LightGBM control (reason: novelty memo V2)

**Reason.** Hand-crafted identifier-transition and graph-topology statistics can carry transferable signal (Khreasat & Villarrubia González, *Sensors* 2026). Without a flat model that receives them, a GraphSAGE advantage over LightGBM cannot be attributed to learned message passing rather than to relational information the flat baseline lacked.

**New model (§7 table, added row):**

| Model | Definition | Role |
|---|---|---|
| **LightGBM+S** | LightGBM on the v1.0 LightGBM input (56 features) **plus the 8 structural statistics below** (64 features). Same tuning grid, selection rule, class weighting and threshold procedure as LightGBM. | explicit-structural-summary control |

**Structural statistics** — computed per window from the directed transition multigraph of §6 (nodes = distinct IDs in the window, *n* = number of nodes; 63 transitions ID(i)→ID(i+1), duplicates and self-loops counted). All are invariant to relabelling of IDs.

| # | Name | Definition |
|---|---|---|
| S1 | transition_entropy | Shannon entropy (bits) of the distribution of distinct directed transitions, each weighted by count/63, divided by log2(63) |
| S2 | unique_transition_ratio | number of distinct directed transitions / 63 |
| S3 | self_loop_ratio | number of transitions with ID(i) = ID(i+1) / 63 |
| S4 | mean_out_degree | number of distinct non-self-loop directed edges / *n* |
| S5 | max_out_degree | maximum over nodes of distinct non-self-loop out-neighbours |
| S6 | max_in_degree | maximum over nodes of distinct non-self-loop in-neighbours |
| S7 | degree_entropy | entropy of the distribution of total degree (in+out, distinct non-self-loop edges) over nodes, divided by log2(*n*); 0 if *n* ≤ 1 |
| S8 | density | distinct non-self-loop directed edges / (*n*(*n*−1)); 0 if *n* ≤ 1 |

Implementation status (VERIFIED on a sample file, 300 windows): vectorised implementation equals a naive reference implementation to within 6e-8; unchanged under random permutation of ID labels.

**What is not changed by C1:** the Rule model still selects from the 56 v1.0 LightGBM features; neural models keep the 4 v1.0 global features (the structural statistics are **not** given to DeepSets, GRU or GraphSAGE); D4 ablation removes only payload-length-derived features, so S1–S8 remain in LightGBM+S under the ablation.

**Hypotheses (§2) — addition:**
- **H3 (secondary):** PR-AUC(GraphSAGE) − PR-AUC(LightGBM+S) on the B cells.
- Also reported (secondary, descriptive of the ladder): PR-AUC(LightGBM+S) − PR-AUC(LightGBM).
- H1 remains the single primary hypothesis. H1a, H2, H3 are secondary and Holm-corrected together with the per-cell secondary tests (§9).

**Interpretation limit to state in the paper (INFERENCE):** H3 contrasts *learned message passing in a neural model* with *explicit summaries in a tree model*, so it differs in model family as well as in how structure is used. It answers "do simple explicit structural summaries in a strong flat learner explain the gain?", not a pure learned-vs-hand-crafted question within one model family.

## Change C2 — Wording of complexity control (reason: claim must match what is implemented)

- The pilot verified that DeepSets (22,850), GRU (22,785) and GraphSAGE (22,657) trainable-parameter counts are within 1% (VERIFIED, k01). This supports the statement **"parameter-matched neural models (±10%) with identical optimiser, schedule, epoch cap, early-stopping and tuning budget."**
- No capacity equivalence is claimed between neural models and tree models or rules. Tree models receive the same number of tuning configurations (8) and the same selection and threshold procedures.
- The phrase "capacity-matched" is not used for the whole model set.

**Contribution statement (replaces memo §4.6 draft):**
> "We conduct a controlled empirical study of whether learned message passing over CAN identifier-transition structure improves intrusion detection under vehicle and attack distribution shift once message-identity information is removed from every model. It is compared with flat learning, flat learning with explicit structural summaries, permutation-invariant aggregation and sequence modelling, with parameter-matched neural models and equal tuning budgets, and a degree-preserving edge-rewiring control tests whether any benefit depends on the observed transition structure."
- "To the best of our knowledge" may be added only after final citation verification; "first" is not used.

## Change C3 — Pre-registered training-selection details (reason: pilot k01)

The pilot showed validation PR-AUC on known-vehicle train_01 folds near ceiling (sanity only; e.g., all models ≈1.00 on one fold), so configuration ties are expected. Fixed now, before tuning:
- **Epoch cap:** 20 (neural models).
- **Early stopping:** per fold, stop when validation PR-AUC has not improved for 3 consecutive epochs; best epoch = epoch of maximum validation PR-AUC (earliest if tied).
- **Configuration selection:** highest mean validation PR-AUC over the two folds. **Tie-break** (applied to all configurations within 0.001 of the best): (1) lower mean validation BCE at each fold's best epoch; (2) fewer mean best epochs; (3) smaller hidden width / fewer leaves; (4) lower learning rate.
- **Final-model epoch count:** rounded mean of the two folds' best epochs (minimum 1).
- **LightGBM / LightGBM+S:** n_estimators cap 1,000 with early stopping after 50 rounds without validation average-precision improvement; the same tie-break with "boosting rounds" in place of epochs.

## Change C4 — Execution detail (reason: pilot k01; §10-permitted)

- The DTU archive download took 3,055 s of the 3,277 s pilot. The dataset is downloaded and SHA-256-verified once in a CPU notebook; its output is attached read-only to all experiment notebooks, which re-verify the 236-file digest before use.

## Change C5 — Dataset naming and related work (reason: novelty review)

- Dataset named as **"can-train-and-test, original release (v1), DTU Data, DOI 10.11583/DTU.24805533.v1"**; the later v1.5 extension (Bitbucket; additional test subsets and attacks, described in Kidmose, Kidmose & Meng, *IJIS* 2025) is not used.
- Related work must include at least: KD-GAT and its VGAE+GAT follow-up; Khreasat & Villarrubia González (*Sensors* 2026); **ACHILLES** (Mowla et al., *IEEE T-ITS* 27(7):7475–7490, 2026, DOI 10.1109/TITS.2026.3688299 — metadata VERIFIED via OpenAlex; meta-learning framework evaluated cross-dataset on four CAN datasets); the obaf cross-vehicle benchmark (publication status to be verified); Lampe & Meng (2024); Koltai et al. (2026); Islam et al. UIDS (2026).

---

## Open alternative (not adopted; recorded for the decision-maker)
A within-family control, **DeepSets+S** (DeepSets with S1–S8 appended to its global features), would contrast learned message passing with explicit structural summaries inside the same neural model family and remove the model-family confound noted under C1. Estimated cost ≈0.7 GPU-hours (pilot projection for DeepSets). Not included, to respect the "no further model proliferation" decision; if a reviewer raises the confound, it is the natural response.

## Resulting model ladder (v1.1)
Rule → LightGBM → **LightGBM+S** → DeepSets → GRU → GraphSAGE → GraphSAGE-rewired.
