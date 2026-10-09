---
name: statistics
description: Experimental design and inference from data, two halves of one question, what a study can conclude. Use whenever the task designs, runs, or benchmarks an experiment or method comparison, analyzes data, writes or reviews results, or draws a conclusion from numbers, a figure, or a table.
---

# Statistics

The design decides what the data can conclude. Random assignment permits causal claims, the replicated unit is the unit of analysis, and a control that differs from the treatment in more than one way leaves the result ambiguous. So check the design first, then check that each conclusion stays within what it licenses. The `logic` skill checks the argument built on top. Record-keeping (result files, timing, rounding) is under Records.

## Design

- State the comparison the study has to make, in one sentence, before collecting data.
- Name the competing explanations and the result each predicts. The design separates them: some outcome favors one and not the others. A design whose every outcome fits every explanation cannot decide between them.
- The control matches the treatment in everything except the active ingredient: expectations, time on task, exposure, compute, tuning effort. A "no treatment" control rarely does.
- Randomize assignment, and blind whoever could bias the measurement. If either is impossible, say why and what stands in for it.
- Decide the unit of replication (subject, animal, seed, dataset) at design time, and replicate that unit. Repeated measurements within a unit do not add independent samples.
- Choose the sample size from a realistic effect size, taken from prior work, not from the effect you hope for.
- Fix in advance the primary comparison, the exclusion rules, and the threshold that counts as success. Label everything else exploratory.
- For exploratory work, hold out data or plan a replication, and define what counts as a real finding before looking.

### Comparing methods

- Compare methods fairly: the same data, splits, preprocessing, and tuning budget. State the baseline and the sample count.
- Benchmark on the settings the baseline papers used, and reproduce their published numbers before comparing.
- Compare per seed or per fold on the same splits, and report the paired differences, not only the gap between means. Show uncertainty when repetitions support it.
- Include at least one setting where the new method underperforms the baseline, and explain why.

## Inference

- Analyze at the unit of replication. Trials within a subject, or cells within an animal, are not independent samples.
- To claim A differs from B, test the difference. "A is significant and B is not" does not show that A and B differ.
- A correlation that one cluster or a few points produce, or that hides subgroups or nonlinearity, does not support a general relation. Plot the raw data.
- Data used to select a feature, region, or model cannot also test it. Split, cross-validate, or fix the selection in advance.
- Report every analysis tried, or justify the one chosen on grounds independent of its result.
- Correct for multiple comparisons, and report effect sizes with intervals, not only p-values.
- Non-significance is not evidence of absence. A wide interval around zero means the data cannot tell. To claim absence, test equivalence.
- Causal words ("causes", "leads to", "produces", "drives") need a design that manipulated the cause. Observational data, however large, support association.
- A result holds for the population, settings, and range that were sampled. Extrapolating beyond them is a new claim that needs its own evidence.

## Records

- Persist experiment results to human-legible JSON (indent the structure but collapse each numeric array onto one line) and drive figures from those files, so restyling is immediate and never needs re-running.
- Always record per-algorithm wall-clock time in the JSON: training (fit) and inference (eval) seconds.
- Round every reported number to the nearest 1/T, where T is the sample size (for a stream, the stream length): round(round(vT)/T, round(log10(T))). One T for all numbers, not a per-metric window. More digits than 1/T is false precision.

## Reporting a statistics finding

- Name the problem: a design that cannot separate the explanations, a mismatched control, the wrong unit, circular selection, a missing difference test, unreported analyses, absence read from non-significance, causal language without manipulation, or extrapolation.
- State the conclusion the design and data do support. Then give the fix: the analysis or control that would support the original claim, or the weaker claim that fits the evidence.
- Severity: a flaw that undoes the central result is Critical. A flaw in a supporting result is Substantive. A wording that overstates a result the data do support is Polish.
