This repository contains example diffusion MRI processing pipelines.

* `tract.sh` – Bash script using FSL tools to preprocess data and run
  probabilistic tractography.
* `tract.py` – Python implementation of a similar workflow
  using DIPY for preprocessing and deterministic tractography.

Both pipelines expect the sample dataset located under `dataset/subj_xx`.
