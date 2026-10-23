![residual-desk](assets/header.png)

# residual-desk

The residual desk is what is left after a cheap first look.

The same twelve calls are routed three ways. **always-big** sends every call to the large model. **rules-then-big** lets a rule close the call, or pays for the large model. **small-judge-then-big** lets a small model keep the call, or pays for the large model. A keep counts as closed only when that tier is allowed to close it. A false close stays open and does not escalate. Prices are illustrative. The run is offline and deterministic. Nothing is sent to a model.

## Run

From the repo root. Python 3.11 or newer. No install and no API key.

```bash
python3 -m residual_desk fixtures/calls.jsonl
python3 -m residual_desk --verbose fixtures/calls.jsonl
python3 -m unittest discover -s tests -v
```

## Score

```
policy                closed  close rate  cost USD
--------------------  ------  ----------  --------
always-big             11/12       91.7%     0.960
rules-then-big         11/12       91.7%     0.664
small-judge-then-big   10/12       83.3%     0.384

Prices are illustrative: rules 0.002, small 0.012, big 0.080 USD per attempt.
```

Twelve calls. The large model closes 11. Rules close the same 11 for 0.664 instead of 0.960. The small judge spends 0.384 and closes 10: it keeps the billing dispute without authority, and that call never reaches the model that could close it. One call, a caller who wants a lawyer, stays open under every policy.

| Policy | What it pays | Close rate | Illustrative cost |
|---|---|---|---|
| always-big | big on every call | 11/12 (91.7%) | 0.960 |
| rules-then-big | rules, then big only on a pass | 11/12 (91.7%) | 0.664 |
| small-judge-then-big | small, then big only on a pass | 10/12 (83.3%) | 0.384 |

## Fixture shape

One JSON object per line. The first line is the price card. Each call says what each tier does (`close` or `pass`) and which tiers may close it.

```json
{"type":"prices","rules":"0.002","small":"0.012","big":"0.080","note":"illustrative"}
{"type":"call","id":"billing-dispute","title":"Partial refund outside the published window","rules":"pass","small":"close","big":"close","can_close":["big"]}
```

`can_close` is the authority. `small: close` on that call is a false close: the small judge stops, the cost stays at 0.012, and the close rate does not move.

## License

MIT
