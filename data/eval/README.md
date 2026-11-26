# Eval question sets (committed, no manual text)

Question sets for measuring search quality. Pages are PDF pages (1-based);
gold values are quoted from the manuals and were verified against rendered
page images (see the `verified_by` field in golden.jsonl).

| File | Size | Shape |
|---|---|---|
| `golden.jsonl` | 10 | `{qid, engine, question, value, gold_pages, verified_by}` — facts with exact values (torque, clearances) |
| `manual.jsonl` | 46 | `{qid, engine, question, gold_pages, kind}` — section lookup with a gold page |
| `negative.jsonl` | 10 | `{qid, engine, fault_code, question}` — questions the manuals cannot answer; the service must refuse (`no_instruction: true`); the fault codes are the six verified "none" cells of the fleet plus the other none cells |

Run:

```bash
python -m rag.eval --set all          # everything
python -m rag.eval --set golden -v    # one set, per-question printout
```

Metrics: hit@1 / hit@5 with a ±1 page tolerance, MRR, the value check for
golden, and the refusal rate for negative. Target (plan-B): hit@5 ≥ 0.85 on
the manual set; the numbers go into the commit message of each stage.

The bulk extracted manual text and the built indexes live in the
gitignored `data/rag/` — only the question sets are committed.
