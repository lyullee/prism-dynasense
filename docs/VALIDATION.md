# Validation and recorded example

This record describes numerical/software checks. No independent experimental validation or regulatory certification is claimed.

## Automated checks

- 43 pytest checks passed locally on Python 3.12.14 / Windows.
- Analytic choked-pressure decay, nozzle branch continuity, area scaling, residual release and closed mass balance.
- Exact ignition boundary and zero pre-ignition dose; inverse-square radiation and dose scaling.
- PRISM dose/probit calls, version and module fingerprint checks.
- Time-grid refinement; actual dose accumulation checked against installed PRISM.
- Sobol estimators checked against additive analytic and Ishigami benchmarks.
- Constant outputs, nonfinite evaluations, invalid input and complete-design requirements.
- Actual CLI outputs, report generation, escaped embedded input and reproducibility fingerprints.
- Desktop (1440 px), mobile (390 px), dark mode (1280 px): no JavaScript errors, page overflow or clipped Sobol labels; output selection and disclosure tested.

## Direct-model example

Seed 20261022; independent uniform five-input ranges; base levels [512, 1024, 2048, 4096]; 300 bootstrap resamples.

Distinct actual model executions: **28,672**; failed executions: **0**. Recorded calculation time: 123.95 s on this development machine (not a general performance guarantee).

| Output | Gate | Maximum ST change | Largest 95% CI half-width |
|---|---|---:|---:|
| released_mass_kg | PASS | 0.000526 | 0.029197 |
| peak_release_kg_s | PASS | 0.000045 | 0.030500 |
| peak_heat_flux_w_m2 | PASS | 0.007796 | 0.047211 |
| thermal_dose | PASS | 0.010770 | 0.078633 |
| conditional_harm_probability | WITHHELD | 0.028712 | 0.167883 |
| dose_at_25pct | PASS | 0.011497 | 0.070302 |
| dose_at_50pct | PASS | 0.010281 | 0.078770 |
| dose_at_75pct | PASS | 0.010731 | 0.078596 |

**7/8 outputs pass the declared gate.** Conditional-harm-probability sensitivity remains withheld because its largest confidence half-width exceeds 0.10. Its model output is computed; the Sobol ranking is not presented as converged. No range or acceptance threshold was changed to force a pass.

## Baseline (synthetic demonstration, not a facility forecast)

| Metric | Actual result |
|---|---:|
| released_mass_kg | 0.1524615396 |
| peak_release_kg_s | 0.01252046397 |
| peak_heat_flux_w_m2 | 10631.01417 |
| thermal_dose | 2448219.402 |
| conditional_harm_probability | 9.954481545e-05 |
| dose_at_25pct | 1958100.407 |
| dose_at_50pct | 2448063.877 |
| dose_at_75pct | 2448219.402 |

Initial inventory 1.033833511 kg; remaining total inventory 0.8813719717 kg. Remaining inventory includes trapped upstream gas and ambient-pressure downstream gas. Inventory closure is constructed from the same state; a separate sampled-rate integration error is also exported (7.02233e-05 kg at the baseline grid).

## Interpretation and limits

Within this illustrative point-source model and these ranges, final-dose total-order indices rank receptor distance, hole diameter, radiant fraction, isolation time, then isolated volume. This is a study-specific variance ranking, not a universal regulatory priority. Close-receptor demonstration inputs make point-source-model limits especially material. They are not evidence for a validated safe distance.

The harm-probability gate illustrates a real uncertainty limit. Software execution success, mass balance and numerical convergence do not validate the flame approximation, assumed radiant fraction, unprotected-exposure probit or real-world event frequency.

Installed-wheel CLI smoke results and pytest/browser machine-readable checks are included in the registration preparation archive. The build environment is recorded in requirements-lock.txt.
