import json
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report

def calculate_metrics(y_true, y_pred):
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average='binary')
    
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }

def print_classification_report(y_true, y_pred):
    print(classification_report(y_true, y_pred, target_names=['Benign', 'Vulnerable']))

def calculate_pairwise_metrics(results):
    """
    results: list of dicts with keys: 'id', 'label', 'pred'
    Assumes IDs are formatted as {base_id}_vuln and {base_id}_fix
    """
    pairs = {}
    for res in results:
        base_id = res['id'].rsplit('_', 1)[0]
        type_suffix = res['id'].rsplit('_', 1)[1] # vuln or fix
        
        if base_id not in pairs:
            pairs[base_id] = {}
        pairs[base_id][type_suffix] = res

    pc = 0 # Pair-wise Correct
    pv = 0 # Pair-wise Vulnerable
    pb = 0 # Pair-wise Benign
    pr = 0 # Pair-wise Reversed
    total_pairs = 0

    for base_id, pair in pairs.items():
        if 'vuln' in pair and 'fix' in pair:
            total_pairs += 1
            vuln_pred = pair['vuln']['pred']
            fix_pred = pair['fix']['pred']
            
            # Ground truth: vuln=1, fix=0
            
            if vuln_pred == 1 and fix_pred == 0:
                pc += 1
            elif vuln_pred == 1 and fix_pred == 1:
                pv += 1
            elif vuln_pred == 0 and fix_pred == 0:
                pb += 1
            elif vuln_pred == 0 and fix_pred == 1:
                pr += 1
                
    metrics = {
        "total_pairs": total_pairs,
        "P-C": pc,
        "P-V": pv,
        "P-B": pb,
        "P-R": pr,
        "P-C_rate": pc / total_pairs if total_pairs > 0 else 0
    }
    return metrics
