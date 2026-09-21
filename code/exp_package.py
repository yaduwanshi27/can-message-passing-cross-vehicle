"""Stage 6 — frozen results package. Reads ONLY the frozen k05 (stats+eval meta) and k06 (audit) outputs and emits the
authoritative tables. No metric is recomputed here except formatting; every number is copied from a named source file.
Usage: python exp_package.py --stats <k05 stats dir> --eval <k05 eval dir> --audit <k06 audit dir> --out /kaggle/working/package"""
import os, json, glob, hashlib, argparse
MODELS = ['Rule', 'LightGBM', 'LightGBM_S', 'DeepSets', 'GRU', 'GraphSAGE', 'GraphSAGE_rewired']
DISP = {'Rule': 'Rule', 'LightGBM': 'LightGBM', 'LightGBM_S': 'LightGBM+S', 'DeepSets': 'DeepSets', 'GRU': 'GRU',
        'GraphSAGE': 'GraphSAGE', 'GraphSAGE_rewired': 'GraphSAGE-rewired'}
ROLE = {'test_01': 'A known/known', 'test_02': 'B unknown vehicle/known attack', 'test_03': 'C known vehicle/unknown attack', 'test_04': 'D unknown/unknown'}
H_LABEL = {'H1': 'H1 GraphSAGE - DeepSets', 'H1a': 'H1a GraphSAGE - GraphSAGE-rewired', 'H2': 'H2 GraphSAGE - GRU',
           'H3': 'H3 GraphSAGE - LightGBM+S', 'ladder_LGBS_minus_LGB': 'LightGBM+S - LightGBM'}
AUD_KEY = {'H1': 'H1_GS_minus_DeepSets', 'H1a': 'H1a_GS_minus_rewired', 'H2': 'H2_GS_minus_GRU', 'H3': 'H3_GS_minus_LGBS',
           'ladder_LGBS_minus_LGB': 'ladder_LGBS_minus_LGB'}

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def f4(x): return f'{x:.4f}'
def pm(x): return f'{x:+.4f}'

def main(STATS, EVAL, AUDIT, OUT):
    os.makedirs(OUT, exist_ok=True)
    R = json.load(open(os.path.join(STATS, 'results.json')))
    A = json.load(open(os.path.join(AUDIT, 'audit.json')))
    T = {}
    # T1 master per-cell PR-AUC
    L = ['cell\trole\trecordings\twindows\tpositives\tprevalence\thours\t' + '\t'.join(DISP[m] + ' PR-AUC (mean+-SD over 5 seeds)' for m in MODELS)]
    for k, c in R['per_cell'].items():
        L.append('\t'.join([k, ROLE[k.split('/')[1]], str(c['n_files']), str(c['windows']), str(c['pos']),
                            f4(c['prevalence_chance_ap']), f'{c["hours"]:.3f}'] +
                           [f"{c['models'][m]['ap_mean']:.4f}+-{c['models'][m]['ap_sd']:.4f}" for m in MODELS]))
    T['T1_master_cells.tsv'] = L
    # T2 attack-family table (tokens with >=50 positive windows in the cell)
    L = ['cell\trole\ttoken\tpositive_windows\t' + '\t'.join(DISP[m] for m in MODELS) + '\tdefinition']
    for k, c in R['per_cell'].items():
        toks = sorted({t for m in MODELS for t in c['models'][m]['per_token']})
        for t in toks:
            for defn, field in (('token recordings only', 'ap_token_recordings_mean'), ('token positives vs all cell negatives', 'ap_token_pos_vs_all_cell_neg_mean')):
                row = [k, ROLE[k.split('/')[1]].split()[0], t, str(c['models'][MODELS[0]]['per_token'][t]['pos'])]
                row += [f4(c['models'][m]['per_token'][t][field]) for m in MODELS]
                L.append('\t'.join(row + [defn]))
    T['T2_attack_family.tsv'] = L
    # T3 hypothesis table: exact enumeration (k06) for B cells and strata; random bootstrap (k05) for non-B cells
    L = ['contrast\tscope\tdifference\tCI95_low\tCI95_high\tCI90_low\tCI90_high\tdecision\tp\tmethod\tn_resamples']
    for h, label in H_LABEL.items():
        ak = AUD_KEY[h]
        for sname, v in A['summary'].get(ak, {}).items():
            L.append('\t'.join([label, sname, pm(v['point_full_sample']), pm(v['ci95'][0]), pm(v['ci95'][1]), pm(v['ci90'][0]), pm(v['ci90'][1]),
                                v['decision'], f"{v['p_exact_two_sided']:.4f}", 'exact per-cell enumeration (k06)', str(v['n_distinct_resamples'])]))
        for k, c in A['cells'].items():
            v = c['exact_bootstrap'][ak]
            L.append('\t'.join([label, k, pm(v['point_full_sample']), pm(v['ci95'][0]), pm(v['ci95'][1]), pm(v['ci90'][0]), pm(v['ci90'][1]),
                                v['decision'], f"{v['p_exact_two_sided']:.4f}", 'exact enumeration (k06)', str(v['n_distinct_resamples'])]))
        for k, c in R['per_cell'].items():
            if k.endswith('test_02'): continue
            v = c['contrasts'][h if h in c['contrasts'] else h]
            L.append('\t'.join([label, k + ' (secondary cell)', pm(v['diff_point']), pm(v['ci95'][0]), pm(v['ci95'][1]), pm(v['ci90'][0]), pm(v['ci90'][1]),
                                v['decision'], f"{v['p_boot_two_sided']:.4f}", 'random bootstrap 2000 (k05)', '2000']))
    L.append('\t'.join(['Holm-adjusted p (family: H1a/H2/H3 B-summary + H1/H1a/H2/H3 per B cell; H1 B-summary is primary and uncorrected)'] + [''] * 10))
    for m, p in sorted(R['holm_family']['p_holm'].items(), key=lambda kv: kv[1]):
        L.append('\t'.join([m, 'Holm (on k05 random-bootstrap p)', '', '', '', '', '', '', f'{p:.4f}', 'k05', '']))
    T['T3_hypotheses.tsv'] = L
    # T4 operating points
    L = ['cell\trole\thours\tmodel\tMacroF1_at_maxF1_threshold\trecall_at_1FAh\tachieved_FAh_at_1FAh\tallowed_FP_1FAh\trecall_at_5FAh\tachieved_FAh_at_5FAh\tallowed_FP_5FAh']
    for k, c in R['per_cell'].items():
        for m in MODELS:
            v = c['models'][m]
            L.append('\t'.join([k, ROLE[k.split('/')[1]].split()[0], f'{c["hours"]:.3f}', DISP[m], f4(v['macro_f1_mean']),
                                f4(v['recall_at_1FAh_mean']), f'{v["achieved_FAh_at_1FAh_mean"]:.2f}', str(v['allowed_fp_test_1FAh']),
                                f4(v['recall_at_5FAh_mean']), f'{v["achieved_FAh_at_5FAh_mean"]:.2f}', str(v['allowed_fp_test_5FAh'])]))
    T['T4_operating_points.tsv'] = L
    # T5 recording-level audit of the B cells
    L = ['cell\trecording\ttoken\twindows\tpositives\tshare_of_cell_positives\tprevalence\t' + '\t'.join(DISP[m] for m in MODELS)
         + '\tLOO_H1_without_this_recording\tLOO_H1_change\tLOO_H1a_without\tLOO_H1a_change']
    for k, c in A['cells'].items():
        for f in c['files']:
            lo = c['leave_one_out'].get(f['file'], {})
            row = [k, f['file'], f['token'], str(f['windows']), str(f['pos']), f4(f['share_of_cell_positives']), f4(f['prevalence'])]
            row += [f4(f['ap_mean'][m]) for m in MODELS]
            row += ([pm(lo['contrasts']['H1_GS_minus_DeepSets']), pm(lo['delta_vs_full']['H1_GS_minus_DeepSets']),
                     pm(lo['contrasts']['H1a_GS_minus_rewired']), pm(lo['delta_vs_full']['H1a_GS_minus_rewired'])] if lo else ['', '', '', ''])
            L.append('\t'.join(row))
    T['T5_recording_audit_B.tsv'] = L
    # T6 variability
    L = ['cell\tmodel\tSD_across_5_seeds\tSD_across_recording_resamples']
    for k, c in A['cells'].items():
        for m in MODELS:
            v = c['seed_vs_recording_variability'][m]
            L.append('\t'.join([k, DISP[m], f4(v['sd_across_seeds']), f4(v['sd_across_recording_resamples'])]))
    T['T6_variability.tsv'] = L
    for name, lines in T.items():
        open(os.path.join(OUT, name), 'w').write('\n'.join(lines) + '\n')
    # provenance
    src = {'k05_results.json': os.path.join(STATS, 'results.json'), 'k06_audit.json': os.path.join(AUDIT, 'audit.json')}
    for p in sorted(glob.glob(os.path.join(EVAL, 'set_*', '*_meta.json'))) + sorted(glob.glob(os.path.join(EVAL, 'set_*', 'id_permutation_test.json'))):
        src['/'.join(p.split(os.sep)[-2:])] = p
    prov = ['file\tsha256\tbytes']
    for nm, p in src.items(): prov.append(f'{nm}\t{sha(p)}\t{os.path.getsize(p)}')
    for name in T: prov.append(f'{name}\t{sha(os.path.join(OUT, name))}\t{os.path.getsize(os.path.join(OUT, name))}')
    open(os.path.join(OUT, 'T0_provenance.tsv'), 'w').write('\n'.join(prov) + '\n')
    for nm in ['T0_provenance.tsv'] + list(T):
        print('\n########', nm)
        print(open(os.path.join(OUT, nm)).read())

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--stats', required=True); ap.add_argument('--eval', required=True); ap.add_argument('--audit', required=True)
    ap.add_argument('--out', default='/kaggle/working/package'); a = ap.parse_args()
    main(a.stats, a.eval, a.audit, a.out)
