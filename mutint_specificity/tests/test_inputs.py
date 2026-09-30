"""What the analysis is run on: which samples are genomes, and which mutations are gene hits."""

from mutint_specificity import params as settings
from mutint_specificity.tests.fixture import SpecificityFixture
from mutint_specificity.util import available_treatments, genomes_for


def options(**overrides):
    chosen = dict(settings.DEFAULTS)
    chosen.update(overrides)
    return chosen


class GenomesTestCase(SpecificityFixture):
    def genomes(self, **overrides):
        genomes, samples, left_out = genomes_for(self.experiment.id, options(**overrides))
        return {g.name: g for g in genomes}, samples, left_out

    def test_treatments_are_the_labels_samples_carry(self):
        from mutint_sample.views.common import get_treatment_names
        self.assertEqual({"cold", "hot"}, set(available_treatments(self.experiment.id)))
        self.assertEqual(get_treatment_names(self.experiment.id),
                         available_treatments(self.experiment.id), "core's order")

    def test_each_sample_with_a_treatment_is_a_genome(self):
        genomes, samples, left_out = self.genomes()
        self.assertEqual({self.h1.label, self.h2.label, self.h3.label, self.hp.label,
                          self.c1.label, self.c2.label, self.c3.label}, set(genomes))
        self.assertEqual("hot", genomes[self.h1.label].treatment)
        self.assertEqual(self.h1.id, samples[self.h1.label])
        self.assertEqual([{"sample": self.b1.label, "sample_id": self.b1.id,
                           "reason": "no treatment"}], left_out)

    def test_synonymous_snps_are_not_gene_hits_by_default(self):
        genomes, _, _ = self.genomes()
        h1 = genomes[self.h1.label]
        self.assertEqual({"geneA"}, h1.genes)
        self.assertEqual(2, h1.n_total, "the synonymous SNP still counts towards the total")
        self.assertEqual("synonymous", h1.mutations[1].snp_class)

    def test_counting_synonymous_snps(self):
        genomes, _, _ = self.genomes(gene_rule=settings.GENE_RULE_ALL)
        self.assertEqual({"geneA", "geneB"}, genomes[self.h1.label].genes)

    def test_nonsynonymous_only(self):
        genomes, _, _ = self.genomes(gene_rule=settings.GENE_RULE_NONSYNONYMOUS)
        self.assertEqual(set(), genomes[self.h2.label].genes, "an INS is not a SNP")
        self.assertEqual({"geneA", "geneC"}, genomes[self.h3.label].genes,
                         "nonsense counts as nonsynonymous")
        self.assertEqual({"geneD"}, genomes[self.c2.label].genes)

    def test_mutations_naming_no_single_gene_count_only_towards_the_total(self):
        genomes, _, _ = self.genomes()
        h3 = genomes[self.h3.label]
        self.assertEqual(4, h3.n_total)
        self.assertEqual(2, h3.n_valid)
        by_type = {m.type: m for m in h3.mutations}
        self.assertEqual(500, by_type["DEL"].size)
        self.assertEqual("IS150", by_type["MOB"].repeat_family)

    def test_excluded_genes(self):
        genomes, _, _ = self.genomes(excluded_genes=["geneA"])
        self.assertEqual(set(), genomes[self.h2.label].genes)
        self.assertEqual(1, genomes[self.h2.label].n_total)

    def test_a_subset_of_treatments(self):
        genomes, _, left_out = self.genomes(treatments=["cold"])
        self.assertEqual({self.c1.label, self.c2.label, self.c3.label}, set(genomes))
        self.assertEqual(["no treatment"], [e["reason"] for e in left_out])

    def test_clones_only(self):
        genomes, _, left_out = self.genomes(clones_only=True)
        self.assertNotIn(self.hp.label, genomes)
        self.assertIn({"sample": self.hp.label, "sample_id": self.hp.id,
                       "reason": "population sample"}, left_out)

    def test_the_ancestor_is_neither_a_genome_nor_counted(self):
        """Designate c1: its geneD mutation is ancestral, so c2 and c3 lose theirs too --
        the subtraction reaches every sample, not only the ancestor's column."""
        self.experiment.set_ancestor(self.c1)
        genomes, _, _ = self.genomes()
        self.assertNotIn(self.c1.label, genomes)
        self.assertEqual({"geneE"}, genomes[self.c2.label].genes)
        self.assertEqual(set(), genomes[self.c3.label].genes)


class SettingsTestCase(SpecificityFixture):
    def test_every_treatment_is_no_narrowing(self):
        chosen = settings.clean({"treatments": ["hot", "cold"]}, ["cold", "hot"])
        self.assertEqual([], chosen["treatments"])
        self.assertEqual(settings.selection_key(chosen),
                         settings.selection_key(settings.clean({}, ["cold", "hot"])))

    def test_a_vanished_treatment_is_dropped(self):
        self.assertEqual(["hot"], settings.clean({"treatments": ["hot", "gone"]},
                                                 ["cold", "hot"])["treatments"])

    def test_a_control_outside_the_analysis_is_refused(self):
        with self.assertRaises(settings.SettingsError):
            settings.clean({"treatments": ["hot"], "control": "cold"}, ["cold", "hot"])

    def test_numbers_are_bounded(self):
        with self.assertRaises(settings.SettingsError):
            settings.clean({"permutations": settings.MAX_PERMUTATIONS + 1}, [])
        with self.assertRaises(settings.SettingsError):
            settings.clean({"alpha": "lots"}, [])

    def test_excluded_genes_are_parsed_and_sorted(self):
        chosen = settings.clean({"excluded_genes": "nadR, pykF  spoT;nadR"}, [])
        self.assertEqual(["nadR", "pykF", "spoT"], chosen["excluded_genes"])

    def test_an_unticked_checkbox_in_a_post_is_false(self):
        from django.http import QueryDict
        chosen = settings.clean(QueryDict("gene_rule=all&permutations=5"), ["hot"])
        self.assertFalse(chosen["pairwise"])
        self.assertTrue(settings.clean({}, ["hot"])["pairwise"], "defaults otherwise")
