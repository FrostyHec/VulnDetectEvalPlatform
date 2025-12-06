#!/usr/bin/env python3
import re
import ast
import json
import csv
import argparse
import os
from datetime import datetime


def parse_configuration(line):
    m = re.search(r"Configuration:\s*(\{.*\})", line)
    if not m:
        return {}
    txt = m.group(1)
    # fallback parse: extract simple 'key': value pairs
    pairs = re.findall(r"'([^']+)'\s*:\s*([^,}]+)", txt)
    cfg = {}
    for k, v in pairs:
        v = v.strip()
        try:
            cfg[k] = ast.literal_eval(v)
        except Exception:
            cfg[k] = v.strip().strip("'")
    return cfg


def try_literal_eval(s):
    try:
        return ast.literal_eval(s)
    except Exception:
        return None


def parse_log(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    meta = {
        'file': path,
        'model_name_or_path': None,
        'output_dir': None,
        'config': {},
        'samples': {},
        'epochs': {},
        'completed': False,
    }

    # regexes
    cfg_re = re.compile(r"Configuration:.*")
    loaded_re = re.compile(r"Loaded\s+(\d+)\s+samples\s+for\s+split\s+'(\w+)'")
    batch_loss_re = re.compile(r"Epoch\s*\[(\d+)/(?:\d+)\].*?loss=([0-9]*\.?[0-9]+)")
    epoch_summary_re = re.compile(r"Epoch\s+(\d+)\s*-\s*Loss:\s*([0-9]*\.?[0-9]+)")
    val_epoch_re = re.compile(r"Validation Results - Epoch\s*(\d+)")
    # loose patterns: look for a {...} that contains accuracy/precision/recall/f1 or total_pairs
    metrics_re = re.compile(r"(\{[^}]*?(?:accuracy|precision|recall|f1)[^}]*\})", re.IGNORECASE)
    pairwise_re = re.compile(r"(\{[^}]*?(?:total_pairs|P-C|P-V|P-B|P-R)[^}]*\})", re.IGNORECASE)
    engine_finished_re = re.compile(r"Engine run finished")

    # scan lines
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # config
        if 'Configuration:' in line and not meta['config']:
            cfg = parse_configuration(line)
            meta['config'] = cfg
            meta['model_name_or_path'] = cfg.get('model_name_or_path') or cfg.get('model_name')
            meta['output_dir'] = cfg.get('output_dir')
            continue

        m = loaded_re.search(line)
        if m:
            cnt = int(m.group(1))
            split = m.group(2)
            meta['samples'][split] = cnt
            continue

        m = batch_loss_re.search(line)
        if m:
            ep = int(m.group(1))
            loss = float(m.group(2))
            ed = meta['epochs'].setdefault(ep, {'batches': [], 'avg_loss': None, 'val_metrics': None, 'pairwise': None})
            ed['batches'].append(loss)
            continue

        m = epoch_summary_re.search(line)
        if m:
            ep = int(m.group(1))
            loss = float(m.group(2))
            ed = meta['epochs'].setdefault(ep, {'batches': [], 'avg_loss': None, 'val_metrics': None, 'pairwise': None})
            ed['avg_loss'] = loss
            continue

        m = val_epoch_re.search(line)
        if m:
            # look ahead for Metrics and Pairwise Metrics (use a longer window and looser matching)
            ep = int(m.group(1))
            metrics = None
            pairwise = None
            # scan next several lines to find dicts containing the expected keys
            for j in range(i+1, min(i+20, len(lines))):
                l2 = lines[j].strip()
                # try metrics first
                mm = metrics_re.search(l2)
                if mm:
                    candidate = mm.group(1)
                    parsed = try_literal_eval(candidate)
                    if isinstance(parsed, dict):
                        # ensure it contains accuracy/precision keys
                        if any(k in parsed for k in ('accuracy', 'precision', 'recall', 'f1')):
                            metrics = parsed
                            continue
                        # sometimes keys may be named differently (e.g., double quotes), still accept
                        metrics = parsed
                        continue
                mm2 = pairwise_re.search(l2)
                if mm2:
                    candidate = mm2.group(1)
                    parsed2 = try_literal_eval(candidate)
                    if isinstance(parsed2, dict):
                        pairwise = parsed2
                        continue
                # fallback: lines that start with Metrics: or Pairwise Metrics: but wrap dict on next line
                if l2.lower().startswith('metrics:'):
                    # attempt to grab subsequent lines until a closing brace
                    buf = l2.partition(':')[2].strip()
                    k = j+1
                    while '}' not in buf and k < min(i+20, len(lines)):
                        buf += lines[k].strip()
                        k += 1
                    parsed = try_literal_eval(buf)
                    if isinstance(parsed, dict):
                        metrics = parsed
                        continue
                if l2.lower().startswith('pairwise metrics:'):
                    buf = l2.partition(':')[2].strip()
                    k = j+1
                    while '}' not in buf and k < min(i+20, len(lines)):
                        buf += lines[k].strip()
                        k += 1
                    parsed2 = try_literal_eval(buf)
                    if isinstance(parsed2, dict):
                        pairwise = parsed2
                        continue
            ed = meta['epochs'].setdefault(ep, {'batches': [], 'avg_loss': None, 'val_metrics': None, 'pairwise': None})
            if metrics:
                ed['val_metrics'] = metrics
            if pairwise:
                ed['pairwise'] = pairwise
            continue

        if engine_finished_re.search(line):
            meta['completed'] = True

    # finalize per-epoch avg loss using batches if needed
    for ep, v in meta['epochs'].items():
        if v['avg_loss'] is None and v['batches']:
            v['avg_loss'] = sum(v['batches']) / len(v['batches'])

    # normalize: sometimes the parser captures pairwise metrics into val_metrics
    for ep, v in meta['epochs'].items():
        vm = v.get('val_metrics')
        pw = v.get('pairwise')
        # if val_metrics contains pairwise keys and pairwise is empty, move it
        if vm and isinstance(vm, dict) and 'total_pairs' in vm and not pw:
            v['pairwise'] = vm
            v['val_metrics'] = None
        # if pairwise exists but val_metrics seems to be missing accuracy keys, keep as-is

    # decide overall completeness
    cfg_epochs = None
    try:
        cfg_epochs = int(meta['config'].get('num_train_epochs'))
    except Exception:
        cfg_epochs = None

    reported_max_epoch = max(meta['epochs'].keys()) if meta['epochs'] else 0
    if meta['completed'] or (cfg_epochs is not None and reported_max_epoch >= cfg_epochs):
        meta['partial'] = False
    else:
        meta['partial'] = True

    meta['parsed_at'] = datetime.utcnow().isoformat() + 'Z'
    return meta


def write_outputs(meta, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(meta['file']))[0]
    json_path = os.path.join(out_dir, f'summary_{base}.json')
    csv_path = os.path.join(out_dir, f'summary_{base}.csv')
    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump(meta, jf, indent=2, ensure_ascii=False)

    # write CSV: one row per epoch
    rows = []
    for ep in sorted(meta['epochs'].keys()):
        e = meta['epochs'][ep]
        row = {
            'file': meta['file'],
            'model': meta.get('model_name_or_path'),
            'epoch': ep,
            'avg_loss': e.get('avg_loss'),
            'batch_count': len(e.get('batches', [])),
            'accuracy': None,
            'precision': None,
            'recall': None,
            'f1': None,
            'pairwise_total_pairs': None,
            'pairwise_P-C': None,
            'pairwise_P-V': None,
            'pairwise_P-B': None,
            'pairwise_P-R': None,
            'pairwise_P-C_rate': None,
        }
        vm = e.get('val_metrics') or {}
        row['accuracy'] = vm.get('accuracy')
        row['precision'] = vm.get('precision')
        row['recall'] = vm.get('recall')
        row['f1'] = vm.get('f1')
        pw = e.get('pairwise') or {}
        row['pairwise_total_pairs'] = pw.get('total_pairs')
        row['pairwise_P-C'] = pw.get('P-C')
        row['pairwise_P-V'] = pw.get('P-V')
        row['pairwise_P-B'] = pw.get('P-B')
        row['pairwise_P-R'] = pw.get('P-R')
        row['pairwise_P-C_rate'] = pw.get('P-C_rate')
        rows.append(row)

    if rows:
        with open(csv_path, 'w', encoding='utf-8', newline='') as cf:
            writer = csv.DictWriter(cf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    # write a compact prompt file for LLM analysis
    prompt_path = os.path.join(out_dir, f'prompt_{base}.txt')
    with open(prompt_path, 'w', encoding='utf-8') as pf:
        pf.write(f"Log file: {meta['file']}\n")
        pf.write(f"Model: {meta.get('model_name_or_path')}\n")
        pf.write("Training config:\n")
        for k in ('train_batch_size', 'eval_batch_size', 'learning_rate', 'num_train_epochs', 'max_len', 'seed', 'logging_steps', 'save_steps'):
            if k in meta.get('config', {}):
                pf.write(f"- {k}: {meta['config'][k]}\n")
        pf.write(f"Samples: train={meta.get('samples', {}).get('train')} val={meta.get('samples', {}).get('val')}\n")
        pf.write(f"Partial log: {meta.get('partial')}\n")
        pf.write('\n')
        pf.write('Per-epoch summary (tab-separated):\n')
        pf.write('epoch\tavg_loss\tbatch_count\taccuracy\tprecision\trecall\tf1\tpairwise_summary\n')
        for ep in sorted(meta['epochs'].keys()):
            e = meta['epochs'][ep]
            vm = e.get('val_metrics') or {}
            pw = e.get('pairwise') or {}
            pairwise_summary = ''
            if pw:
                pairwise_summary = ','.join(f"{k}={pw.get(k)}" for k in ('total_pairs','P-C','P-V','P-B','P-R','P-C_rate') if k in pw)
            pf.write(f"{ep}\t{e.get('avg_loss')}\t{len(e.get('batches', []))}\t{vm.get('accuracy') if vm else ''}\t{vm.get('precision') if vm else ''}\t{vm.get('recall') if vm else ''}\t{vm.get('f1') if vm else ''}\t{pairwise_summary}\n")

    return json_path, csv_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('logs', nargs='+', help='paths to log files to parse')
    p.add_argument('--out', default='src/scripts/log_analysis/out', help='output directory')
    args = p.parse_args()

    results = []
    for lp in args.logs:
        if not os.path.isfile(lp):
            print('skip (not a file):', lp)
            continue
        print('parsing', lp)
        meta = parse_log(lp)
        jpath, cpath = write_outputs(meta, args.out)
        print('wrote', jpath, cpath)
        results.append({'file': lp, 'json': jpath, 'csv': cpath})

    # summary
    summary_path = os.path.join(args.out, 'summary_index.json')
    with open(summary_path, 'w', encoding='utf-8') as sf:
        json.dump({'generated_at': datetime.utcnow().isoformat() + 'Z', 'files': results}, sf, indent=2)
    print('summary index ->', summary_path)


if __name__ == '__main__':
    main()
