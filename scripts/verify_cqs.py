# scripts/verify_cqs.py

def run_queries(graph, cqs, label, key="query"):
    """Run each CQ's `key` query on graph. Return (checked, failures)."""
    checked = failures = 0
    for cq in cqs or []:
        query = cq.get(key)
        if not query:
            continue
        checked += 1
        cq_id = cq.get("id") or cq.get("question", "?")
        try:
            results = list(graph.query(query))
        except Exception as e:
            print(f"FAIL [{label}] {cq_id}: query error: {e}")
            failures += 1
            continue
        if results:
            print(f"PASS [{label}] {cq_id}: {len(results)} result(s)")
        else:
            print(f"FAIL [{label}] {cq_id}: 0 results")
            failures += 1
    return checked, failures
