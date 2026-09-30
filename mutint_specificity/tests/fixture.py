"""An experiment built row by row, with the annotation a real import would have written.

`single_gene_affected` is written by `mutint_import.annotation.annotation_values` from the
reference; here it is set directly on `Mutation.annotation`, which is where that function
puts it, so the inputs can say exactly which mutation names which gene.

Two treatments, three samples each, plus one sample with no treatment and one population
sample:

    hot:  h1 {geneA, geneB}   h2 {geneA}           h3 {geneA, geneC}
    cold: c1 {geneD}          c2 {geneD, geneE}    c3 {geneD}
    blank:   b1 (no treatment)
    hot:     hp (population sample) {geneA}

The cold samples' geneD is one mutation observed in all three. h1's geneB is a synonymous
SNP; h3 also carries an intergenic DEL of 500 bp and an IS150
insertion that names no gene.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from mutint_experiment.models import Experiment, Population
from mutint_sample.models import Mutation, MutationCall, Sample


class SpecificityFixture(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="owner", email="o@e.com", is_active=True)
        self.client.force_login(self.user)
        created = self.client.post(
            "/project/create/", {"name": "P", "experiment": "E"}).json()
        self.experiment = Experiment.objects.get(pk=created["experiment_id"])
        self.position = 0

        self.h1 = self.sample("hot", "h1", "hot")
        self.h2 = self.sample("hot", "h2", "hot")
        self.h3 = self.sample("hot", "h3", "hot")
        self.c1 = self.sample("cold", "c1", "cold")
        self.c2 = self.sample("cold", "c2", "cold")
        self.c3 = self.sample("cold", "c3", "cold")
        self.b1 = self.sample("blank", "b1", "")
        self.hp = self.sample("hot", "hp", "hot", clonal=False)

        self.observe(self.h1, self.mutation("SNP", "geneA", "nonsynonymous"))
        self.observe(self.h1, self.mutation("SNP", "geneB", "synonymous"))
        self.observe(self.h2, self.mutation("INS", "geneA"))
        self.observe(self.h3, self.mutation("SNP", "geneA", "nonsense"))
        self.observe(self.h3, self.mutation("SNP", "geneC", "nonsynonymous"))
        self.observe(self.h3, self.mutation("DEL", None, size=500))
        self.observe(self.h3, self.mutation("MOB", None, repeat_name="IS150"))
        gene_d = self.mutation("SNP", "geneD", "nonsynonymous")   # one site, three samples
        self.observe(self.c1, gene_d)
        self.observe(self.c2, gene_d)
        self.observe(self.c2, self.mutation("DEL", "geneE", size=3))
        self.observe(self.c3, gene_d)
        self.observe(self.b1, self.mutation("SNP", "geneA", "nonsynonymous"))
        self.observe(self.hp, self.mutation("SNP", "geneA", "nonsynonymous"))

    def sample(self, population, name, treatment, clonal=True):
        row, _ = Population.objects.get_or_create(experiment=self.experiment, name=population)
        return Sample.objects.create(population=row, time_point=100, name=name,
                                     is_clonal=clonal, treatment=treatment, source_name=name)

    def mutation(self, kind, gene, snp_type="", size=None, repeat_name=None):
        self.position += 100
        annotation = {"single_gene_affected": gene} if gene else {}
        record = {"type": kind, "seq_id": "chr", "position": self.position}
        if size is not None:
            record["size"] = size
        if repeat_name is not None:
            record.update(repeat_name=repeat_name, strand=1, duplication_size=5)
        return Mutation.objects.create(
            experiment=self.experiment, mutation_type=kind, seq_id="chr",
            start_position=self.position, sequence_change="%s%d" % (kind, self.position),
            snp_type=snp_type if kind == "SNP" else "", gene=gene or "intergenic",
            annotation=annotation,
            supplemental_data={"mutint_core": {"genome_diff": record}})

    def observe(self, sample, mutation):
        return MutationCall.objects.create(sample=sample, mutation=mutation, present=True,
                                           frequency=1.0)
