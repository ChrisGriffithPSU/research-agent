# PSE-2: Branch Selection + Hypothesis Registry

Role: Planning Agent. Do not write code.

## Purpose

Convert the chosen solution-space branch into a ranked set of falsifiable, atomic hypotheses with discriminating tests.

This phase must:
- enforce falsifiability,
- define what evidence would kill each hypothesis,
- define what evidence would promote each hypothesis,
- define how hypotheses discriminate between one another.

## Required MCP Tool Calls

1) thoughtbox get_model model="assumption-surfacing"
2) thoughtbox get_model model="inversion"
3) thoughtbox get_model model="impact-effort-grid"

Optional (only if you must choose between competing approaches):
4) thoughtbox get_model model="trade-off-matrix"

## Inputs

Requires approved artifacts from PSE-0 and PSE-1:
- Session Charter
- Event Spec
- Solution Space Tree
- User-selected BRANCH

## Outputs (Artifacts)

Produce these artifacts using templates in `problem-solving/11_artifact_templates.mdc`:
- Hypothesis Registry

Also output:
- a Discriminating Test Matrix (tests x hypotheses)
- a Hypothesis Test Batch Plan that covers the entire branch

## Procedure (Algorithm)

1) Re-anchor to the branch
   1.1) Restate the chosen branch claim in 1 sentence.
   1.2) List the top 3 reasons it might fail (from the tree node).

2) Enumerate branch-local assumptions
   2.1) Use Assumption Surfacing on this branch specifically.
   2.2) Convert each assumption into a verification hook that can be executed as an assumption check in PSE-3/PSE-4.
       - Assumptions must be structural (about the object), not pipeline/data-validation statements.

3) Generate hypotheses (atomic and falsifiable)
   3.1) Generate a comprehensive set of hypotheses for the branch.
       - Target size: 20-60 hypotheses for a normal branch.
       - If the branch is narrow, minimum is 12.
   3.2) Each hypothesis must be written as:
       "If X (mechanism/structure), then observable Y within Z under conditions C."
   3.3) Each hypothesis must include:
       - mechanism (or UNKNOWN, but then it is Track B)
       - >=2 predictions
       - 1 discriminating test with binary outcome definition
       - minimal viable experiment concept
       - explicit kill criteria and promote criteria
   3.4) Label each as Track A or Track B.

4) Define discriminating tests
   4.1) For each hypothesis, propose the smallest test that would kill it.
   4.2) Prefer tests that kill multiple hypotheses.

5) Prior assignment and ranking
   5.1) Assign a prior in [0, 1] for each hypothesis.
   5.2) Rank hypotheses by:
       - expected information gain per unit effort
       - prior
       - risk of confounding/leakage
   5.3) Identify "gateway" hypotheses that must be answered first.

6) Discriminating Test Matrix
   6.1) Create a matrix:
       rows = candidate tests
       cols = hypotheses
       cell value in {kills, supports, irrelevant}
   6.2) Use the matrix to define a small set of gateway tests that maximally discriminate the hypothesis set.

7) Build the Hypothesis Test Batch Plan
   7.1) Group hypotheses into test batches that can be executed in one scaffold pass.
       - Each batch must have a named purpose (baseline, comparison, normalization, conditioning, confound/null, symmetry).
       - Each batch must state which hypotheses it targets and what outputs it will produce.
   7.2) Order batches by expected information gain per unit effort.

8) Output and request approval
   8.1) Output Hypothesis Registry.
   8.2) Output Discriminating Test Matrix.
   8.3) Output the Hypothesis Test Batch Plan.
   8.4) Ask the user to:
       - APPROVE PSE-2
       - or REVISE PSE-2: <specific corrections>

## Exit Criteria

PSE-2 is complete only when:
- Hypothesis Registry has a comprehensive set of hypotheses for the selected branch,
- Discriminating Test Matrix is provided,
- Hypothesis Test Batch Plan is provided,
- user responds `APPROVE PSE-2`.

---

## F) Hypothesis Registry (HR)

```text
Hypothesis Registry
===================

hypotheses:
  - hypothesis_id: <H1>
    track: <A|B>
    statement: "If <X>, then <observable Y> within <Z> under <conditions>."
    mechanism: <string or UNKNOWN>
    predictions:
      - <prediction 1>
      - <prediction 2>
    discriminating_test:
      test_name: <string>
      binary_outcome_definition:
        true_if: <rule>
        false_if: <rule>
    minimal_viable_experiment: <one line>
    prior: <0-1>
    kill_criteria: <explicit>
    promote_criteria: <explicit>
    status: <proposed|active|killed|promoted>
    notes: <string>
```

## F2) Hypothesis Test Batch Plan (HTBP)

```text
Hypothesis Test Batch Plan
==========================

branch_id: <node_id>

batches:
  - batch_id: <B1>
    purpose: <baseline|comparison|normalization|conditioning|confound_null|symmetry|other>
    hypotheses_targeted: <list of hypothesis_ids>
    required_inputs: <what data/artifacts are needed>
    outputs: <what metrics/tables/artifacts are produced>
    pass_fail_contract:
      pass_if: <explicit>
      fail_if: <explicit>
    notes: <string>
```

---

```text
Hypothesis Registry
===================

hypotheses:
  - hypothesis_id: H1
    track: A
    statement: "If bid/ask depletion asymmetry leads repricing, then multi-level book OFI(L1-L5, W=500ms) separates up-events from matched controls within 5s."
    mechanism: pre-event pressure and fragility build before repricing.
    predictions:
      - median(OFI|up_event) > median(OFI|control) within matched buckets
      - tail_ratio_q90 > 1.15 in eligible slices
    discriminating_test:
      test_name: holdout_auc_and_null
      binary_outcome_definition:
        true_if: holdout AUC >= 0.53 and time-shift null AUC in [0.49, 0.51]
        false_if: holdout AUC < 0.53 or time-shift null AUC >= 0.53
    minimal_viable_experiment: compute feature on holdout for top variants selected from dev and evaluate AUC + null
    prior: 0.55
    kill_criteria: false_if
    promote_criteria: true_if
    status: proposed
    notes: core effect existence test

  - hypothesis_id: H2
    track: A
    statement: "If deeper levels carry incremental intent, then OFI(L1-L5) outperforms OFI(L1) on the same matched sample."
    mechanism: slope/deeper depletion reveals fragility beyond L1 flicker.
    predictions:
      - AUC(L1-L5) - AUC(L1) >= 0.01 on dev
      - slice stability improves (more slices with consistent sign)
    discriminating_test:
      test_name: paired_auc_diff
      binary_outcome_definition:
        true_if: AUC_diff >= 0.01
        false_if: AUC_diff <= 0.00
    minimal_viable_experiment: compute L1 and L1-L5 variants and compare AUC on identical window set
    prior: 0.60
    kill_criteria: AUC_diff <= 0.00
    promote_criteria: AUC_diff >= 0.01
    status: proposed
    notes: validates Session Charter assumption A2

  - hypothesis_id: H3
    track: A
    statement: "If level weights should emphasize near-touch liquidity, then monotone weights (1/l) outperform uniform weights across levels."
    mechanism: top levels are more actionable; deeper levels provide context.
    predictions:
      - AUC(1/l weights) >= AUC(uniform) on dev
      - tails improve (q90 tail ratio increases)
    discriminating_test:
      test_name: weight_scheme_compare
      binary_outcome_definition:
        true_if: AUC_gain >= 0.005
        false_if: AUC_gain <= 0.00
    minimal_viable_experiment: compare two weight schemes with same W,k
    prior: 0.50
    kill_criteria: AUC_gain <= 0.00
    promote_criteria: AUC_gain >= 0.005
    status: proposed
    notes: constrains weighting choice without overfitting

  - hypothesis_id: H4
    track: A
    statement: "If time-of-day liquidity scale is a confound, then depth-normalized OFI improves slice stability and holdout AUC."
    mechanism: dimensionless scaling improves invariance.
    predictions:
      - between-bucket drift of OFI medians decreases under normalization
      - holdout AUC improves relative to raw
    discriminating_test:
      test_name: normalization_stability_and_auc
      binary_outcome_definition:
        true_if: drift_reduction >= 20% and holdout AUC improves
        false_if: drift_reduction < 10% and holdout AUC does not improve
    minimal_viable_experiment: raw vs depth-normalized variants
    prior: 0.55
    kill_criteria: false_if
    promote_criteria: true_if
    status: proposed
    notes: validates assumption A3

  - hypothesis_id: H5
    track: A
    statement: "If OFI is conditional on fragility, then thin+spread=1 slices have materially higher AUC than wide-spread slices."
    mechanism: response-time and fragility differ by spread/liquidity.
    predictions:
      - AUC(thin, spread=1) - AUC(spread>1) >= 0.03
      - AUC(spread>1) ~ 0.50
    discriminating_test:
      test_name: slice_lift
      binary_outcome_definition:
        true_if: slice_lift >= 0.03 and wide_spread_auc in [0.49, 0.51]
        false_if: slice_lift < 0.01
    minimal_viable_experiment: slice report on dev then confirm on holdout
    prior: 0.65
    kill_criteria: slice_lift < 0.01
    promote_criteria: slice_lift >= 0.03
    status: proposed
    notes: validates assumption A4

  - hypothesis_id: H6
    track: A
    statement: "If OFI is not purely reactive, then excluding any pre-t0 mid movement does not collapse AUC."
    mechanism: leading pressure exists before first tick move.
    predictions:
      - AUC drop under pre-move exclusion <= 0.02
      - lead/lag shows OFI rises before first +1 tick
    discriminating_test:
      test_name: pre_move_exclusion
      binary_outcome_definition:
        true_if: AUC_drop <= 0.02
        false_if: AUC_drop > 0.03
    minimal_viable_experiment: enforce mid(t0)=mid(t0-1s) subset and reevaluate
    prior: 0.50
    kill_criteria: AUC_drop > 0.03
    promote_criteria: AUC_drop <= 0.02
    status: proposed
    notes: validates assumption A5

  - hypothesis_id: H7
    track: A
    statement: "If OFI is symmetric, then the same feature definition separates down-events with sign flip similarly to up-events."
    mechanism: symmetric pressure.
    predictions:
      - |AUC_up - AUC_down| <= 0.02
      - medians flip sign
    discriminating_test:
      test_name: symmetry_check
      binary_outcome_definition:
        true_if: auc_gap <= 0.02 and medians flip sign
        false_if: auc_gap > 0.03
    minimal_viable_experiment: evaluate down-event classification on holdout
    prior: 0.55
    kill_criteria: auc_gap > 0.03
    promote_criteria: auc_gap <= 0.02
    status: proposed
    notes: validates assumption A6

  - hypothesis_id: H8
    track: A
    statement: "If OFI signal is concentrated in tails, then a tail-conditioned indicator (OFI > q90_control) yields stronger separation than raw OFI."
    mechanism: events arise from extreme pressure pockets.
    predictions:
      - tail ratio is large and stable across slices
      - monotonic relationship in OFI quantiles
    discriminating_test:
      test_name: tail_concentration
      binary_outcome_definition:
        true_if: tail_ratio_q90 >= 1.20 and monotonicity holds in >= 3 quantile bins
        false_if: tail_ratio_q90 <= 1.05
    minimal_viable_experiment: quantile bucket analysis
    prior: 0.45
    kill_criteria: tail_ratio_q90 <= 1.05
    promote_criteria: tail_ratio_q90 >= 1.20
    status: proposed
    notes: supports feature shaping decisions

  - hypothesis_id: H9
    track: A
    statement: "If OFI must reflect persistence, then OFI computed over W=500ms outperforms W=250ms and W=1000ms (broad plateau)."
    mechanism: too short is flicker; too long dilutes.
    predictions:
      - AUC(W=500ms) >= AUC(W=250ms)
      - AUC(W=500ms) >= AUC(W=1000ms)
    discriminating_test:
      test_name: window_sweep
      binary_outcome_definition:
        true_if: 500ms is best or tied-best within 0.005
        false_if: 500ms is worst by >0.01
    minimal_viable_experiment: window sweep on dev; confirm top 2 on holdout
    prior: 0.50
    kill_criteria: 500ms worst by >0.01
    promote_criteria: 500ms best/tied
    status: proposed
    notes: controls param family selection

  - hypothesis_id: H10
    track: A
    statement: "If multi-level OFI is not brittle, then k=3,5,10 produce similar holdout performance (no sharp dependence)."
    mechanism: pressure manifests across nearby levels.
    predictions:
      - holdout AUC(k=3..10) within 0.02 range
      - k=1 is worse
    discriminating_test:
      test_name: level_sweep
      binary_outcome_definition:
        true_if: max_auc(k=3,5,10)-min_auc(k=3,5,10) <= 0.02 and AUC(k=1) lower
        false_if: k choice swings AUC by >0.03
    minimal_viable_experiment: level sweep on dev; confirm on holdout
    prior: 0.45
    kill_criteria: k swings AUC by >0.03
    promote_criteria: plateau holds
    status: proposed
    notes: guards against brittle tuning

  - hypothesis_id: H11
    track: A
    statement: "If trade-based cum-delta is mostly confound under matching, then its AUC is near 0.50-0.52 and does not beat book OFI."
    mechanism: trades are reactive; matching removes time-of-day/vol effects.
    predictions:
      - AUC(cum-delta) < AUC(book OFI)
      - null tests are clean
    discriminating_test:
      test_name: baseline_compare
      binary_outcome_definition:
        true_if: AUC_cum_delta <= 0.52 and AUC_book_ofi >= AUC_cum_delta + 0.02
        false_if: cum-delta dominates book OFI
    minimal_viable_experiment: baseline compute
    prior: 0.60
    kill_criteria: cum-delta dominates
    promote_criteria: baseline confirmed
    status: proposed
    notes: sanity baseline

  - hypothesis_id: H12
    track: B
    statement: "If a time-of-day rank transform is safe when fit-only-on-train, then it improves stability without inflating null tests."
    mechanism: UNKNOWN (exploratory transform)
    predictions:
      - stability improves vs raw/normalized
      - null AUC remains ~0.50
    discriminating_test:
      test_name: rank_transform_safety
      binary_outcome_definition:
        true_if: stability improves and null AUC in [0.49, 0.51]
        false_if: null AUC >= 0.53
    minimal_viable_experiment: implement train-only fit rank transform and verify null
    prior: 0.20
    kill_criteria: null AUC >= 0.53
    promote_criteria: pass -> must graduate to Track A with mechanism + falsifiers
    status: proposed
    notes: quarantine by default until null proves safety

  - hypothesis_id: H13
    track: A
    statement: "If OFI is meaningful only in certain regimes, then gating to (thin, spread=1) increases information density even if overall sample shrinks."
    mechanism: conditionality and subtraction-first.
    predictions:
      - AUC in gated slice improves
      - effect is stable across time-of-day buckets within gated slice
    discriminating_test:
      test_name: gating_value
      binary_outcome_definition:
        true_if: gated AUC >= ungated AUC + 0.02 and sign stability improves
        false_if: gated AUC does not improve
    minimal_viable_experiment: compare gated vs ungated performance surfaces
    prior: 0.55
    kill_criteria: gated AUC does not improve
    promote_criteria: gated improves
    status: proposed
    notes: sets up subtraction-first usage

  - hypothesis_id: H14
    track: A
    statement: "If OFI effect is real, then a within-bucket permutation null produces an AUC distribution centered at 0.50 and observed AUC is in the upper tail."
    mechanism: multiple-testing defense.
    predictions:
      - permuted mean ~0.50
      - observed AUC percentile >= 90th (coarse)
    discriminating_test:
      test_name: permutation_null_percentile
      binary_outcome_definition:
        true_if: observed percentile >= 90
        false_if: observed percentile <= 60
    minimal_viable_experiment: run 200 permutations within (regime,time_bucket)
    prior: 0.50
    kill_criteria: observed percentile <= 60
    promote_criteria: percentile >= 90
    status: proposed
    notes: protects against accidental p-hacking

  - hypothesis_id: H15
    track: A
    statement: "If OFI reflects book fragility rather than price drift, then conditioning on last-1s mid return does not eliminate OFI separation."
    mechanism: pressure distinct from momentum.
    predictions:
      - correlation(OFI, last_1s_return) is low/moderate
      - incremental AUC vs last_1s_return baseline is positive
    discriminating_test:
      test_name: redundancy_incremental
      binary_outcome_definition:
        true_if: incremental AUC >= +0.02 in gated slices
        false_if: incremental AUC <= +0.005
    minimal_viable_experiment: baseline model vs baseline+OFI
    prior: 0.45
    kill_criteria: incremental AUC <= +0.005
    promote_criteria: incremental AUC >= +0.02
    status: proposed
    notes: information density check

  - hypothesis_id: H16
    track: A
    statement: "If the feature is robust, then performance does not come from one day/week; holdout sub-block AUCs are consistent."
    mechanism: OOS survival.
    predictions:
      - AUC across holdout sub-blocks within 0.03 range
      - confidence intervals overlap
    discriminating_test:
      test_name: holdout_block_stability
      binary_outcome_definition:
        true_if: max_auc-min_auc <= 0.03
        false_if: max_auc-min_auc > 0.05
    minimal_viable_experiment: split holdout into 3 blocks
    prior: 0.50
    kill_criteria: max_auc-min_auc > 0.05
    promote_criteria: max_auc-min_auc <= 0.03
    status: proposed
    notes: temporal clumping check

  - hypothesis_id: H17
    track: A
    statement: "If spoof/mirage liquidity can fake OFI, then false positives concentrate in high-churn conditions even within thin+spread=1."
    mechanism: mirage liquidity produces OFI spikes without follow-through.
    predictions:
      - FP windows have higher churn proxy than TP windows
      - conditional AUC drops in high churn bucket
    discriminating_test:
      test_name: fp_signature_churn
      binary_outcome_definition:
        true_if: churn(TP) < churn(FP) by a material margin and high-churn AUC degrades
        false_if: churn does not discriminate failures
    minimal_viable_experiment: analyze top false positives and compare churn proxy
    prior: 0.55
    kill_criteria: churn does not discriminate failures
    promote_criteria: churn discriminates
    status: proposed
    notes: sets up adversarial review inputs

  - hypothesis_id: H18
    track: A
    statement: "If absorption/resiliency neutralizes OFI, then false positives concentrate in high replenishment/resiliency conditions."
    mechanism: replenishment offsets depletion.
    predictions:
      - FP windows have higher replenishment proxy than TP windows
      - conditional AUC drops in high resiliency bucket
    discriminating_test:
      test_name: fp_signature_resiliency
      binary_outcome_definition:
        true_if: replenishment(FP) > replenishment(TP) and high-resiliency AUC degrades
        false_if: replenishment does not discriminate failures
    minimal_viable_experiment: failure analysis by replenishment proxy
    prior: 0.50
    kill_criteria: replenishment does not discriminate failures
    promote_criteria: replenishment discriminates
    status: proposed
    notes: sets up subtraction-first transform candidates

  - hypothesis_id: H19
    track: A
    statement: "If OFI is causal-order-correct, then swapping to a future-looking OFI window ([t0, t0+500ms]) should not predict as well as past-looking OFI."
    mechanism: time directionality.
    predictions:
      - future OFI AUC ~0.50 under strict anti-leakage
      - past OFI AUC > future OFI AUC
    discriminating_test:
      test_name: time_directionality_guard
      binary_outcome_definition:
        true_if: AUC_past - AUC_future >= 0.02 and AUC_future ~0.50
        false_if: AUC_future similar to AUC_past
    minimal_viable_experiment: compute past and (intentionally wrong) future window under controlled test harness
    prior: 0.35
    kill_criteria: AUC_future similar to AUC_past
    promote_criteria: time directionality holds
    status: proposed
    notes: adversarial guard against accidental leakage

  - hypothesis_id: H20
    track: A
    statement: "If OFI is meaningful, then OFI should increase event probability smoothly across quantiles, not only in a single hot bin."
    mechanism: robust monotone pocket rather than one-bin artifact.
    predictions:
      - quantile event rates show monotone-ish pattern
      - pattern persists in holdout
    discriminating_test:
      test_name: monotonicity
      binary_outcome_definition:
        true_if: Spearman corr(signal_quantile, event_rate) > 0.2 and stable OOS
        false_if: no monotonicity and only one bin is hot
    minimal_viable_experiment: quantile bucketing in dev then confirm in holdout
    prior: 0.45
    kill_criteria: only one hot bin
    promote_criteria: monotone-ish
    status: proposed
    notes: protects against overpartition illusions
```

Hypothesis Test Batch Plan:

```text
Hypothesis Test Batch Plan
==========================

branch_id: A2

batches:
  - batch_id: B1
    purpose: baseline
    hypotheses_targeted: [H11]
    required_inputs: trades, matched windows
    outputs: baseline AUC + null
    pass_fail_contract:
      pass_if: baseline is weak (serves as comparison)
      fail_if: baseline dominates book OFI (forces branch reconsideration)
    notes: sanity baseline for later incremental claims

  - batch_id: B2
    purpose: comparison
    hypotheses_targeted: [H2, H3]
    required_inputs: L2 depth snapshots
    outputs: paired AUC diff (L1 vs L1-L5) and weight scheme compare
    pass_fail_contract:
      pass_if: multi-level + monotone weights help
      fail_if: no improvement over L1
    notes: validates whether A2 branch is worth pursuing

  - batch_id: B3
    purpose: normalization
    hypotheses_targeted: [H4]
    required_inputs: L2 depth snapshots
    outputs: raw vs depth-normalized AUC + drift reduction table
    pass_fail_contract:
      pass_if: stability improves and AUC improves
      fail_if: normalization harms or no effect
    notes: validates invariance assumption

  - batch_id: B4
    purpose: conditioning
    hypotheses_targeted: [H5, H13]
    required_inputs: regime labels, time buckets
    outputs: slice AUC surfaces; gated vs ungated comparison
    pass_fail_contract:
      pass_if: fragile-state lift exists
      fail_if: no conditional structure
    notes: subtraction-first setup

  - batch_id: B5
    purpose: confound_null
    hypotheses_targeted: [H6, H14, H19]
    required_inputs: mid prices, null test engine
    outputs: pre-move exclusion AUC; permutation null percentile; time-directionality guard
    pass_fail_contract:
      pass_if: non-reactive and nulls are clean
      fail_if: confound/leakage signatures
    notes: required for mechanism plausibility and robustness

  - batch_id: B6
    purpose: symmetry
    hypotheses_targeted: [H7]
    required_inputs: labels for down events
    outputs: down-event AUC and sign flip checks
    pass_fail_contract:
      pass_if: symmetric
      fail_if: unexplained asymmetry
    notes: sanity check

  - batch_id: B7
    purpose: robustness
    hypotheses_targeted: [H9, H10, H16, H20]
    required_inputs: window sweep, level sweep, holdout sub-blocks
    outputs: sensitivity surfaces; block stability; monotonicity report
    pass_fail_contract:
      pass_if: broad plateaus and no temporal clumping
      fail_if: brittle tuning or clumping
    notes: decides whether to enter deep investigation

  - batch_id: B8
    purpose: failure_cases
    hypotheses_targeted: [H17, H18]
    required_inputs: churn proxy, replenishment proxy, TP/FP labeling
    outputs: failure signature discriminators
    pass_fail_contract:
      pass_if: structured failures exist (enables subtraction)
      fail_if: failures are random
    notes: feeds PSE-6 adversarial review
```