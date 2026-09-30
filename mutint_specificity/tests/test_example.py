"""The example dataset loads, and gives the answer its README states.

It is the real thing -- the TEE clones of Deatherage et al. 2017 against the REL606
reference -- so this is also the one test that runs the whole path: import, annotation into
`single_gene_affected`, the ancestor designated by `load_example`, and evospec on top.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from mutint_experiment.models import Experiment
from mutint_specificity import params as settings
from mutint_specificity.util import available_treatments, genomes_for

EXPECTED_TREATMENTS = {"20C": 6, "32C": 6, "32C/42C": 6, "37C": 6, "42C": 6}


class ExampleTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store = tempfile.mkdtemp()
        with override_settings(MUTINT_STORE_DIR=cls.store):
            User.objects.create(username="admin", email="a@e.com", is_active=True,
                                is_superuser=True)
            call_command("load_example", "mutint-specificity-example",
                         stdout=StringIO(), stderr=StringIO())
        cls.experiment = Experiment.objects.get(name="mutint-specificity-example")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.store, ignore_errors=True)

    def test_rel1207_is_the_ancestor(self):
        self.assertEqual("REL1207", self.experiment.ancestor.source_name)

    def test_thirty_clones_in_five_treatments(self):
        self.assertEqual(sorted(EXPECTED_TREATMENTS), sorted(available_treatments(
            self.experiment.id)))
        genomes, _, left_out = genomes_for(self.experiment.id, dict(settings.DEFAULTS))
        self.assertEqual([], left_out)
        counts = {}
        for genome in genomes:
            counts[genome.treatment] = counts.get(genome.treatment, 0) + 1
        self.assertEqual(EXPECTED_TREATMENTS, counts)

    def test_the_answer_in_the_readme(self):
        from evospec import analyze

        genomes, _, _ = genomes_for(self.experiment.id, dict(settings.DEFAULTS))
        result = analyze(genomes, permutations=2000, seed=0)
        grand = result["dice"]["comparisons"][0]
        self.assertGreater(grand["within"], grand["between"])
        self.assertEqual(0, grand["randomized_at_least"])
        significant = {r["gene"] for r in result["genes"]["rows"] if r["significant"]}
        self.assertTrue({"hslU", "nadR"} <= significant, significant)
