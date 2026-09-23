# STAGE 2 DESIGN ADDENDUM v1.2: attention-based message-passing extension (GAT)

**Status:** FROZEN before any GAT run. **Frozen:** 2026-09-22. **Decision authority:** user ("strengthen first", then "choose what is necessary", 2026-09-22). **Written by:** Claude (worker).
**Relation to v1.0/v1.1:** additive only. Nothing in v1.0/v1.1, `RESULTS_FROZEN_v1.0` or `ROBUSTNESS_RESULTS_v1.0` changes.
**Timing disclosure (must appear in the paper):** this extension was specified **after** the original results were known. It answers the pre-submission criticism that only one, mean-aggregating message-passing architecture was tested. It is therefore an **extension analysis, specified before it was run**, not part of the original pre-specified protocol. Whatever its outcome, it is reported.

## 1. Question
Does an attention-based message-passing aggregator, given the same identity-free node information, change the answer to RQ1? In other words, is the null GraphSAGE–DeepSets result specific to mean aggregation?

## 2. Models (identity-free; same inputs as GraphSAGE)
- **GAT.** Two message-passing layers of the same form as GraphSAGE:
  **h**ᵥ⁽ˡ⁺¹⁾ = ReLU(**Θ**ₛ**h**ᵥ⁽ˡ⁾ + Σᵤ αᵤᵥ **Θ**ₙ**h**ᵤ⁽ˡ⁾).
  The attention αᵤᵥ = softmaxᵤ( LeakyReLU₀.₂( **a**ᵀ[**Θ**ₙ**h**ᵤ ‖ **Θ**ₙ**h**ᵥ] ) + log Aᵤᵥ ) is taken over the observed incoming transitions u→v. There are K = 4 heads, whose outputs are concatenated (H/4 channels each).
  - The log Aᵤᵥ term keeps the transition multiplicities that GraphSAGE uses. With **a** = 0 the layer reduces exactly to GraphSAGE's transition-weighted mean. GAT therefore differs from GraphSAGE **only** by learned attention, and receives the same information.
  - Nodes with no incoming transition receive a zero neighbour message, as in GraphSAGE.
  - The pooling head is identical to DeepSets and GraphSAGE (sum/mean/max + window features → two-layer MLP).
- **GAT-rewired.** GAT trained and evaluated on the degree-preserving rewired graphs, using the same rewiring function, the same per-batch randomisation in training and the same fixed evaluation seed (12345).

## 3. Tuning, selection and training (identical rules to v1.0/v1.1)
- **Grid:** 8 configurations: learning rate {1e-3, 3e-4} × width {matched to GraphSAGE hidden 32 or 64} × dropout {0, 0.2}. The GAT width is chosen so its trainable parameters match GraphSAGE's at that grid point within 10%, with the width divisible by 4.
- **Tuning:** two-fold recording-level cross-fitting on train_01 only, the same folds as k03. AdamW, batch size 1024, weighted binary cross-entropy, at most 20 epochs, patience 3, selection by mean validation AP, and the v1.1 tie-break.
- **GAT-rewired:** uses GAT's selected configuration without separate tuning.
- **Final models:** retrained on the whole train_01 partition for the rounded mean of the two folds' best epochs, with 5 seeds (0–4).
- **Normalisation:** training statistics; at test, training-constant inputs are set to 0 (as in k05 v2); float32.
- **Thresholds:** 1 and 5 FA/h, and max-F1, from pooled out-of-fold scores, as in k04.

## 4. Evaluation
- **Cells:** the four B cells (test_02) only. This is the primary condition of the study.
- **Protocol:** every test file is SHA-256-verified, and no file may be identical to its set's train_01.
- **Comparators:** k05's frozen per-window scores for DeepSets and GraphSAGE. Windows are asserted identical to k05 (same y, file_id and starts).
- **Metrics:** window-level PR-AUC (seed mean); achieved FA/h at the nominal thresholds.

## 5. Contrasts and decision rule (unchanged rule)
- **E1:** GAT − DeepSets. **E1a:** GAT − GAT-rewired. **E2:** GAT − GraphSAGE.
- Each is reported on the B summary, the same- and cross-manufacturer strata, and per cell. Uncertainty comes from exact enumeration of the attack-family-stratified recording bootstrap; the B summary uses 200,000 draws from the exact per-cell distributions (the k06 code).
- **Decision rule:** superior or inferior if the 95% interval excludes 0; practically equivalent if the 90% interval lies within ±0.02; otherwise inconclusive.
- **Multiplicity:** Holm across the three B-summary tests (E1, E1a, E2) using the exact p-values. Per-cell results are descriptive.

## 6. Reporting commitments
- All outcomes are reported, including a GAT advantage.
- If GAT > DeepSets, the paper's conclusion narrows: the null result is specific to mean aggregation.
- The extension is labelled as specified after the original results.
- No retuning of any original model and no change to the original numbers.

## 7. Stopping rule
One tuning run, one final-training run and one evaluation run. A crash may be re-run only if it occurs before any test metric is computed; the reason is logged in `RUN_LOG`.
