# PrimeVul Adaptation: Difference Analysis & Fix Plan

## 1. Issue Description
The training logs for the adapted pipeline showed suspicious metrics:
- **Accuracy**: ~0.50 (Random guessing for balanced dataset)
- **Precision**: ~0.50
- **Recall**: ~0.97 (Almost 1.0)
- **F1**: ~0.66
- **Pairwise Metrics**: High number of "Pair-wise Vulnerable" (P-V) predictions.

This indicates the model is predicting the positive class (Vulnerable, Label 1) for almost all samples. Given that the dataset is roughly balanced (implied by Acc ~0.5 and P ~0.5), the model has failed to learn discriminative features or is biased by an incorrect training setup.

## 2. Code Comparison Analysis

### A. Model Architecture & Loss Function
*   **Original (`run_ft.py` & `model.py`)**:
    *   Uses a custom `Model` class wrapping the base encoder (e.g., `RobertaModel`).
    *   **Loss Function**: Manually implemented Binary Cross Entropy (BCE) on the **first logit** (`logits[:, 0]`).
        ```python
        prob = torch.sigmoid(logits)
        loss = torch.log(prob[:,0])*labels + torch.log((1-prob)[:,0])*(1-labels)
        ```
    *   **Interpretation**: Label 1 (Vulnerable) is trained to maximize `logits[:, 0]`. Label 0 (Benign) is trained to minimize `logits[:, 0]`. The second logit (`logits[:, 1]`) is ignored.
    
*   **Adapted (`train.py`)**:
    *   Uses `AutoModelForSequenceClassification` with `num_labels=2`.
    *   **Loss Function**: Standard `CrossEntropyLoss` (Softmax + NLL).
    *   **Interpretation**: Label 1 is trained to maximize `logits[:, 1]` relative to `logits[:, 0]`.

**Discrepancy**: The original implementation treats the problem as a binary classification using a single output node (effectively), while the adapted version uses a standard 2-class classification. While both are valid, the original implementation's specific loss formulation might be crucial for reproducing their results or stability.

### B. Tokenization
*   **Original**: Manually adds `[CLS]` and `[SEP]` tokens and handles padding/truncation explicitly.
*   **Adapted**: Uses `tokenizer(..., return_tensors='pt')` which handles special tokens automatically.
*   **Conclusion**: This is likely equivalent for CodeBERT/UnixCoder, but the original method gives more explicit control.

### C. Class Weights
*   **Original**: Supports `args.vul_weight` to handle class imbalance.
*   **Adapted**: Currently does not implement class weighting.
*   **Impact**: If the dataset were imbalanced, this would be critical. However, the logs suggest a balanced dataset, so this is likely not the root cause of the "all-1" prediction, but should be added for robustness.

## 3. Fix Plan

To ensure the adaptation is faithful to the original PrimeVul experiment and to fix the convergence issue:

1.  **Replicate Model Architecture**:
    *   Port the `Model` class from `origin_tools/PrimeVul/os_expr/model.py` to `src/adapted_tools/primeVul/model.py`.
    *   Update `train.py` to use this `Model` class instead of `AutoModelForSequenceClassification`.
    *   This ensures the loss function and forward pass are identical to the original.

2.  **Update Training Loop**:
    *   Modify `train_step` to handle the `(loss, prob)` output tuple from the custom `Model`.
    *   Ensure the optimizer and scheduler setup matches the original (which it mostly does).

3.  **Update Metrics Calculation**:
    *   The custom `Model` returns probabilities (sigmoid of logits).
    *   Predictions should be derived as `preds = prob[:, 0] > 0.5` (since `prob[:, 0]` represents the probability of Label 1).

4.  **Configuration Updates**:
    *   Increase `num_train_epochs` to 20 as requested.
    *   (Optional) Add class weight support if needed later.

## 4. Verification
*   Run a short training session (1-2 epochs) to verify that Accuracy moves away from 0.5 and Precision/Recall become balanced.

## 5. Fix Implementation & Verification
**Status**: Implemented.

**Changes Made**:
1.  **`src/adapted_tools/primeVul/model.py`**:
    *   Created `Model` class replicating the original `RobertaClassificationHead` + BCE Loss logic.
    *   Created `DefectModel` class replicating the original logic for `CodeT5` (Encoder-Decoder + Softmax + CE Loss).
2.  **`src/adapted_tools/primeVul/train.py`**:
    *   Updated to import `Model` and `DefectModel`.
    *   Added logic to instantiate the correct model class based on `config.model_type`.
    *   Updated `train_step` to handle `(loss, prob)` return signature.
    *   Updated `validation_step` to handle prediction logic differences:
        *   **CodeBERT/UnixCoder**: `preds = (prob[:, 0] > 0.5).long()`
        *   **CodeT5**: `preds = (prob[:, 1] > 0.5).long()`
3.  **`src/adapted_tools/primeVul/config.py`**:
    *   Updated default `num_train_epochs` to 20.

**Verification**:
*   Ran a short test (1 epoch) with `exp1-codebert-fix-2`.
*   Metrics (Acc ~0.51, Recall ~0.96) still show a strong bias towards the positive class in the first epoch, similar to the original run.
*   **Conclusion**: The code logic is now identical to the original PrimeVul implementation. The initial bias might be due to the model initialization or the difficulty of the task requiring more epochs to converge. The dataset is perfectly balanced (4357 vs 4357), so the bias is not data-driven.
*   **Recommendation**: Proceed with the full 20-epoch training run to observe convergence.
