# mutint-specificity

A [MutInt](https://github.com/mutint/mutint) plugin that asks whether genome evolution was
specific to the treatment each population evolved under.

It compares the genes mutated in samples from different treatments, using the Dice similarity
with a randomization test. It also finds signature genes concentrated in one treatment (Fisher's
exact test), and compares mutation counts and types across treatments. This is the analysis of
Deatherage *et al.* 2017, *PNAS* 114:E1904
([doi:10.1073/pnas.1616132114](https://doi.org/10.1073/pnas.1616132114)). The statistics come from
the [evospec](https://github.com/barricklab/evospec) package.

It adds a **Specificity** page to each experiment. The analysis runs as a background job, and
the results are cached until the experiment's mutations change. It also provides an example
dataset:

```bash
./mutint load_example mutint-specificity-example
```

`docs/using/specificity.md` is the user guide, and `CLAUDE.md` covers development and tests.

MIT licensed; see `LICENSE`.
