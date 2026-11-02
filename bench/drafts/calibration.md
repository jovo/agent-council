# Temperature scaling after fine-tuning

## Question

Fine-tuned classifiers are often overconfident. We ask whether temperature scaling, fit on a held-out split, reduces expected calibration error (ECE) on in-distribution test data without lowering accuracy.

## Method

We fine-tuned a ResNet-50 on CIFAR-100 with five seeds. For each seed we fit one temperature on a validation split of 5,000 images, disjoint from the training and test images, by minimizing negative log-likelihood. The baseline is the same model without scaling. Both use the same checkpoints, so the comparison isolates the effect of the temperature.

## Results

| | Accuracy (%) | ECE (%) |
|---|---|---|
| Baseline | 78.4 ± 0.3 | 9.1 ± 0.6 |
| Temperature scaling | 78.4 ± 0.3 | 2.3 ± 0.4 |

Across the five seeds, scaling lowered ECE by 6.8 points (paired difference, range 6.1 to 7.5) and left accuracy unchanged, as expected, since a single temperature does not change the ranking of classes.

## Scope

These results hold for CIFAR-100 test data drawn from the training distribution. We did not test shifted data, where a temperature fit in-distribution is known to underperform.
