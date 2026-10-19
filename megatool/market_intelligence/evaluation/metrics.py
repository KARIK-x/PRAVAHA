"""Classification metrics for model evaluation (Part 20/29).
stdlib-only: precision, recall, F1, macro-F1, confusion matrix."""
from __future__ import annotations


def confusion_matrix(y_true: list[str], y_pred: list[str]) -> dict:
    labels = sorted(set(y_true) | set(y_pred))
    matrix = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        matrix[t][p] += 1
    return {"labels": labels, "matrix": matrix}


def precision_recall_f1(y_true: list[str], y_pred: list[str]) -> dict:
    cm = confusion_matrix(y_true, y_pred)
    labels = cm["labels"]
    matrix = cm["matrix"]
    per_label = {}
    f1s = []
    for lbl in labels:
        tp = matrix[lbl][lbl]
        fp = sum(matrix[t][lbl] for t in labels if t != lbl)
        fn = sum(matrix[lbl][p] for p in labels if p != lbl)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_label[lbl] = {"precision": round(prec, 4), "recall": round(rec, 4),
                          "f1": round(f1, 4), "support": tp + fn}
        f1s.append(f1)
    acc = (sum(matrix[l][l] for l in labels) / len(y_true)) if y_true else 0.0
    return {
        "per_label": per_label,
        "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
        "accuracy": round(acc, 4),
        "n": len(y_true),
        "confusion": cm,
    }
