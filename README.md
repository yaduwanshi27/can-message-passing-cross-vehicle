# Does Learned Message Passing Improve Cross-Vehicle CAN Intrusion Detection? An Identity-Controlled Evaluation

Code, frozen protocol and audit material for the manuscript by Rashmi Yaduwanshi, Shailesh D. Kamble and Ritesh Yaduwanshi (submitted to *IEEE Transactions on Intelligent Transportation Systems*).

The study tests whether learned message passing (GraphSAGE) over identifier-transition graphs improves CAN intrusion detection on a vehicle not seen in training, once the arbitration identifier is withheld from every model. GraphSAGE is compared with a permutation-invariant set model given the same node features (DeepSets), a degree-preserving rewired control, a GRU, LightGBM with and without explicit graph statistics, and a single-feature rule.

## Data
The experiments use **can-train-and-test v1** (B. Lampe, DTU Data, doi:[10.11583/DTU.24805533.v1](https://doi.org/10.11583/DTU.24805533.v1), CC BY 4.0). The dataset is not redistributed here. `audit/DATASET_FILE_MANIFEST_STAGE1B.csv` lists every one of the 236 CSV files with its SHA-256 digest; the pipeline refuses any file whose digest differs.

## Repository layout
| Folder | Contents |
|---|---|
| `protocol/` | The design frozen before any test partition was read (`STAGE2_DESIGN_FROZEN_v1.0.md`, 2026-09-17) and its amendment (`v1.1`), also fixed before test data were read, plus the extension addendum `STAGE2_DESIGN_ADDENDUM_v1.2_GAT.md` (2026-09-22), frozen before the extension run but after the original results were known. |
| `audit/` | The dataset integrity audit (duplicates, partition checks, exclusion of set_01/test_04) and the file manifest with SHA-256 digests. |
| `code/` | Python modules: identity-free features (`feats.py`), models (`models.py`), tuning (`exp_tune.py`), final training (`exp_final.py`), test scoring (`exp_eval.py`), statistics (`exp_stats.py`), recording-level exact-enumeration audit (`exp_audit.py`), result package (`exp_package.py`), the sensitivity analyses at other window lengths (`featsW.py`, `modelsW.py`, `exp_robust.py`, `robust_stats.py`), and the attention-based extension (`GATLayer`/`GAT` in `models.py`, `exp_gat.py`, `gat_stats.py`). |
| `notebooks/` | The Kaggle notebooks exactly as run, in order k00 to k09. |

## Reproducing the results
The notebooks were run on Kaggle (2× NVIDIA Tesla T4, Python 3.12, PyTorch 2.10.0 with CUDA 12.8, the Kaggle image's LightGBM). Run them in order:

1. `k00` — download the dataset and verify the archive MD5 and all file digests.
2. `k01` — engineering pilot (feature invariance to identifier permutation; parameter counts).
3. `k02` — verified data cache.
4. `k03` — tuning by two-fold recording-level cross-fitting on each training partition only.
5. `k04` — final models, five seeds.
6. `k05` — the only run that reads test partitions; scores all models and computes the statistics.
7. `k06` — exact enumeration of the attack-family-stratified recording bootstrap.
8. `k07` — result tables.
9. `k08` — pre-specified sensitivity analyses (payload-length ablation, window lengths 32 and 128, in-span negatives).
10. `k09` — extension analysis: attention-based aggregation (GAT and its rewired control) on the unknown-vehicle cells, under the rules of `protocol/STAGE2_DESIGN_ADDENDUM_v1.2_GAT.md`. This analysis was specified after the original results were known and frozen before it was run; it reuses the k03 folds and the k05 evaluation windows, both verified by assertion, and retunes no original model.

Approximate GPU time: tuning 1.05 h, final training 0.53 h, test scoring 0.38 h, sensitivity analyses 2.93 h, extension analysis 2.18 h (T4×2, wall clock 7,832 s).

## Licence
Code: MIT Licence (`LICENSE`). Documents: CC BY 4.0.

## Citation
If you use this material, please cite the article (citation to be added on publication).
