# mutint-specificity-example: the thermal tolerance experiment

Thirty *E. coli* clones, one from each of thirty populations evolved for 2000 generations at
constant 20°C, 32°C, 37°C or 42°C, or alternating between 32°C and 42°C. Each treatment has six
populations, Ara−1 to Ara−3 and Ara+1 to Ara+3. They come from Deatherage *et al.* 2017, *PNAS*
114:E1904 ([doi:10.1073/pnas.1616132114](https://doi.org/10.1073/pnas.1616132114)).

- **The mutations** are the curated `.gd` files in
  [LTEE-Ecoli](https://github.com/barricklab/LTEE-Ecoli)'s `TEE-clone-curated/`.
- **The reference** is REL606 from the same repository, as breseq's GFF3.
- **The ancestor** is REL1207, the Ara+ ancestor, which the registration designates. Its
  mutations are subtracted from every clone.
- **REL1206**, the Ara− ancestor, is left out. It lacks only the *araA* marker SNP that REL1207
  carries (REL606:70867), and REL1207 can stand in for both ancestors. Subtracting REL1207 also
  subtracts that marker from the Ara+ clones, and the Ara− clones never had it.

`metadata.csv` places every clone. Each treatment's populations are named after it, for example
`32C Ara-1`. The `.gd` headers alone would have filed 32°C Ara−1 and 42°C Ara−1 together as
population `-1`.

## The expected answer

These are the default settings: every mutation except synonymous SNPs counts as a gene hit, and
the seed is 0. With 100 000 randomizations:

| Treatment | Clones | Mutations | Gene hits |
|---|---|---|---|
| 20C | 6 | 32 | 27 |
| 32C | 6 | 37 | 29 |
| 37C | 6 | 23 | 22 |
| 42C | 6 | 36 | 26 |
| 32C/42C | 6 | 31 | 26 |

**Dice similarity, all treatments.** Within treatments it is 0.162, and between treatments
0.041. No randomization reached that difference: p < 1e-05.

**Signature genes** (Fisher's exact test, p ≤ 0.05):

| Gene | Concentrated in | Clones hit | p |
|---|---|---|---|
| *nadR* | 32C | 6 of 6, and none elsewhere | 1.7e-06 |
| *hslU* | 37C | 5 of 6, and 2 elsewhere | 8.3e-04 |
| *gltB* | 20C | 4 of 6, and 1 elsewhere | 0.0026 |
| *mrdA* | 42C | 4 of 6, and 1 elsewhere | 0.0026 |

Eight genes hit twice in one treatment and never elsewhere are also significant, each at
p = 0.034:

- 20C: *metL*, *nusA*, *spoT* and *yliG*
- 32C/42C: *aceB* and *mreC*
- 42C: *yfgA*
- 32C: *yijC*

*iclR* is hit six times across three treatments and is not significant (p = 0.075).

**Without those twelve genes**, the Dice difference disappears: within 0.026, between 0.038,
p = 0.82. The specificity is carried by the signature genes.

`mutint_specificity/tests/test_example.py` asserts the parts that do not depend on how many
randomizations are run.
