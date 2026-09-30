# Specificity of evolution

The **Specificity** page asks whether evolution was specific to the treatment each population
evolved under. It uses the analysis of
[Deatherage *et al.* 2017](https://doi.org/10.1073/pnas.1616132114), through the
[evospec](https://github.com/barricklab/evospec) package, and answers four questions:

- **Dice similarity.** Were samples from the same treatment mutated in more of the same genes
  than samples from different treatments? This is tested by randomly reassigning samples to
  treatments many times.
- **Genes.** For each gene, are the samples with a mutation in it concentrated in one
  treatment? (Fisher's exact test.)
- **Mutation counts.** Did some treatments accumulate more mutations? (Mann–Whitney and
  Kruskal–Wallis tests, optionally against a control treatment.)
- **Mutation types.** How many SNPs, deletions, amplifications, insertions and IS insertions
  did each treatment accumulate?

## Before you start

Give every sample its **treatment**, either on the experiment's **Samples** page or in the
`treatment` column of a `metadata.csv` imported with the data. A sample without a treatment
is left out, and the page names it. If the experiment has an **ancestor**, designate it: its
mutations are subtracted from every sample before anything is counted.

The analysis compares **genomes**, so it is meant for clones. Tick **Clones only** to leave out
population samples.

## What counts as a gene hit

A mutation counts towards a gene when breseq's annotation names **exactly one gene**, in any of
three ways:

- the mutation inactivates it;
- the mutation overlaps it;
- the mutation lies in its promoter, within 150 bases upstream of its start.

A mutation spanning several genes, or between two genes, counts towards the sample's total but
not towards any gene.

By default a synonymous SNP is not a gene hit. **Gene hits** can instead count every mutation,
or only nonsynonymous and nonsense SNPs. **Genes to leave out** drops genes you name, for example
ones known to mutate in every condition.

The page uses these settings rather than your view filter. Every mutation called in a sample
counts, whatever its frequency.

The evospec command line assigns genes from a GenBank file, with its own promoter length and
with repeat regions set aside. Its gene hits can therefore differ slightly from this page's.

## Running it

Press **Run**. The analysis runs as a background job and the page shows its progress. It reloads
when the analysis finishes, and **Cancel** stops it. If a job waits for a long time, check
that a worker is running (`./mutint start` runs them). The job is also listed on **Jobs**.

- **Randomizations.** 10 000 gives p-values to about 1e-4; the paper used 1 000 000.
- **Seed.** The same seed gives the same answer.
- **Reusing results.** Pressing **Run** with the same settings shows the stored answer.
  **Run again** recomputes it.
- **When results are discarded.** A stored answer is thrown away when the experiment's
  mutations change, for example after an import, an edit or a new ancestor.

Both tables can be downloaded as CSV: the genes, and the genes-by-samples matrix.

## An example

```bash
./mutint load_example mutint-specificity-example
```

This loads the thirty clones of the thermal tolerance experiment, with REL1207 as the ancestor.
Its README, in `mutint_specificity/examples/tee/`, gives the answer to expect: *nadR* at 32°C,
*hslU* at 37°C, *mrdA* at 42°C and *gltB* at 20°C.
