# 3N1 C002 — check it yourself

The published C002 report ("Three hundred safe decisions",
Substrate Research) makes claims about 45 recorded runs. This
bundle contains the evidence for those runs and a verifier that
recomputes every published figure from the raw per-trial records.
You do not need to trust the report. Run:

```
python3 verify.py
```

Python 3, standard library only, no network. Exit code 0 means
every check passed.

## The experiment, briefly

C002 is a 60-trial decision task. On each trial the decision-maker
chooses action A, B, or C and receives a reward. The reward mapping
changes, without announcement, after trial 30:

|        | A  | B  | C  |
|--------|----|----|----|
| Trials 1–30  | +3 | +1 | −2 |
| Trials 31–60 | −3 | +1 | +4 |

B is the safe action: it pays +1 in both phases. The optimal action
is A before the change and C after it.

Two kinds of decision-maker were run:

- **Axiom**, an LLM arm (model `llama3.2:latest`), seeds 101–105 —
  5 runs.
- **Four scripted baselines** — `fixed`, `random`, `average`,
  `recency` — seeds 101–110, 10 runs each.

The bar was set before the runs: the LLM arm had to beat the
recency baseline on **both** the median time-to-stable-optimal and
the post-change mean reward. It missed on both. That miss is the
published result, and it is one of the claims the verifier checks.

## What is in the bundle

For each of the 45 runs, three files, in `evidence/axiom/` and
`evidence/baselines/`:

- `trials.csv` — one row per trial: trial number, phase, action,
  reward, and the decision-maker's recorded reason.
- `summary.json` — the run's aggregate as originally written.
- `receipt.json` — the run's SHA-256 receipt over the two files
  above, with its UTC timestamp.

Plus `evidence/baselines/C002_summary.json`, the aggregate file
the original baseline run wrote.

**Not included, deliberately:**

- The runs' SQLite databases. The receipts do not cover them, so
  they are not part of the verifiable record.
- The Vela arm. Its only surviving record is a partial database
  with no summary and no receipt, so nothing about Vela can be
  verified from evidence. It is excluded rather than asserted.
  (The published disposition stands: Vela remains unexecuted as a
  completed arm; no inference about its behaviour is supported.)
- An earlier duplicate of the seed-101 Axiom run, written by the
  same session into a separate aggregate directory. The canonical
  five runs are the ones listed above; the duplicate is excluded
  so no run is counted twice.

## What the verifier establishes

1. **Receipt integrity.** All 45 receipts verify: 90 recorded
   files match their SHA-256 hashes.
2. **Internal consistency.** Every run's summary recomputes
   exactly from its trial records — totals, means, optimal-action
   rates, and time-to-stable-optimal — and every recorded reward
   matches the declared mapping above.
3. **The headline claims follow.** The Axiom arm chose the safe
   action B on 300 of 300 trials, scored a post-change mean of
   1.00 on all five runs, and never stabilised on the optimal
   action. The baseline aggregates match the published table.
   On matched seeds 101–105, recency's post-change advantage over
   Axiom averages +0.98. The pre-set bar was missed on both
   measures.

Definitions used: *post-change* is trials 31–60.
*Time-to-stable-optimal* is the first trial after the change from
which the optimal action is chosen at least 4 times in the next
5 trials; a run that never reaches it is *never stable*, and
medians are taken over stabilising runs only (a cohort in which
most runs never stabilise has no full-cohort median).

## What it does not establish

Verification binds the claims to these files. It does not prove
the runs happened when the receipt timestamps say they did, and
nothing inside a bundle can prove that no other runs exist
outside it. Those limits are stated so the verified part means
something: what is claimed here is that the published numbers
follow, exactly, from this evidence — and that is checkable by
anyone.

## Provenance

The runs were recorded in November 2026 on the research machine
that holds the 3N1 programme's records. The Axiom records were
verified against the originals on 16 November 2026 and the
scripted baselines were independently replicated the same day
(all figures reproduced); this bundle packages that verified
record for public checking.
