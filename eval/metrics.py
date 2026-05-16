"""Evaluation metrics for ablation suites."""


def recall_at_k(retrieved_ids, relevant_ids, k):
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant) / len(relevant)


def mrr(retrieved_ids, relevant_ids):
    relevant = set(relevant_ids)
    for idx, item in enumerate(retrieved_ids, start=1):
        if item in relevant:
            return 1.0 / idx
    return 0.0


def f1(predicted, actual):
    pred = set(predicted)
    gold = set(actual)
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    precision = tp / len(pred)
    recall = tp / len(gold)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def multi_hop_success(found_hops, required_hops):
    return set(required_hops) <= set(found_hops)


def temporal_success(predicted, expected):
    return predicted == expected
