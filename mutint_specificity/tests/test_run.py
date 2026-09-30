"""Running an analysis: the page, the job, the cache and its discarding.

The suite's task backend is immediate, so a POST runs the analysis inside the request and the
redirect lands on a finished run. The cancellation tests switch to the database backend,
where a launch only queues -- the mutint-fastqc precedent.
"""

from django.contrib.auth.models import AnonymousUser, User
from django.test import override_settings

from mutint_common.rebuild_registry import request_rebuild, run_rebuilds
from mutint_jobs.models import Job
from mutint_specificity import params as settings
from mutint_specificity import tasks, util
from mutint_specificity.models import (
    STATUS_CANCELLED,
    STATUS_FINISHED,
    STATUS_QUEUED,
    SpecificityRun,
)
from mutint_specificity.tests.fixture import SpecificityFixture

DATABASE_TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}


class RunTestCase(SpecificityFixture):
    def url(self):
        return "/specificity/?experiment_id=%d" % self.experiment.id

    def run_it(self, **fields):
        data = {"treatments": ["hot", "cold"], "gene_rule": settings.GENE_RULE_NOT_SYNONYMOUS,
                "permutations": 200, "seed": 1, "alpha": 0.05, "pairwise": "1"}
        data.update(fields)
        return self.client.post(self.url(), data)

    def test_the_page_renders_with_nothing_run(self):
        response = self.client.get(self.url())
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "P</a>: E</b> - Specificity")
        self.assertContains(response, 'value="hot"')
        self.assertNotContains(response, "Dice similarity of mutated genes")

    def test_the_sidebar_has_the_entry(self):
        response = self.client.get(self.url())
        self.assertContains(response, 'href="/specificity/?experiment_id=%d"' % self.experiment.id)

    def test_running_answers_on_the_page(self):
        response = self.run_it()
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)
        run = SpecificityRun.objects.get()
        self.assertEqual(STATUS_FINISHED, run.status)
        self.assertIsNotNone(run.job_id, "the run is attributed on /jobs/")
        self.assertEqual(run.job.task_result_id, run.task_result_id)

        result = run.result
        self.assertEqual(["hot", "cold"], result["treatments"])
        self.assertEqual([self.b1.label], [e["sample"] for e in result["left_out"]])
        gene_a = next(r for r in result["genes"]["rows"] if r["gene"] == "geneA")
        self.assertEqual({"hot": 4, "cold": 0}, gene_a["genomes"])

        page = self.client.get(self.url())
        self.assertContains(page, "Dice similarity of mutated genes")
        self.assertContains(page, "<i>geneA</i>")
        self.assertContains(page, "/specificity/download/%d/genes.csv" % run.pk)

    def test_a_control_treatment_is_compared_with_the_others(self):
        self.run_it(control="cold")
        run = SpecificityRun.objects.get()
        tests = run.result["counts"]["tests"]["total"]
        self.assertEqual(["hot"], [e["treatment"] for e in tests["vs_control"]])
        page = self.client.get(self.url())
        self.assertContains(page, "cold vs hot")
        self.assertContains(page, "Total excluding cold")

    def test_the_same_settings_reuse_the_run(self):
        self.run_it()
        first = SpecificityRun.objects.get()
        self.run_it()
        self.assertEqual([first.pk], list(SpecificityRun.objects.values_list("pk", flat=True)))

    def test_run_again_replaces_it(self):
        self.run_it()
        first = SpecificityRun.objects.get()
        self.run_it(again="1")
        second = SpecificityRun.objects.get()
        self.assertNotEqual(first.pk, second.pk)

    def test_different_settings_are_a_different_run(self):
        self.run_it()
        self.run_it(gene_rule=settings.GENE_RULE_ALL)
        self.assertEqual(2, SpecificityRun.objects.count())

    def test_the_settings_are_remembered(self):
        self.run_it(permutations=321, excluded_genes="geneC")
        page = self.client.get(self.url())
        self.assertContains(page, 'value="321"')
        self.assertContains(page, "geneC</textarea>")

    def test_a_bad_setting_is_said_on_the_page(self):
        response = self.run_it(control="nowhere")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "not one of the treatments analyzed")
        self.assertFalse(SpecificityRun.objects.exists())

    def test_signed_out_readers_cannot_run(self):
        self.experiment.project.is_public = True
        self.experiment.project.save()
        self.client.logout()
        self.assertEqual(200, self.client.get(self.url()).status_code)
        self.assertEqual(403, self.run_it().status_code)
        self.assertFalse(SpecificityRun.objects.exists())

    def test_a_reader_without_access_is_refused(self):
        stranger = User.objects.create(username="stranger", email="s@e.com", is_active=True)
        self.run_it()
        run = SpecificityRun.objects.get()
        self.client.force_login(stranger)
        self.assertEqual(403, self.client.get(self.url()).status_code)
        self.assertEqual(404, self.client.get("/specificity/status/%d" % run.pk).status_code)
        self.assertEqual(404, self.client.get(
            "/specificity/download/%d/genes.csv" % run.pk).status_code)

    def test_status_and_downloads(self):
        self.run_it()
        run = SpecificityRun.objects.get()
        state = self.client.get("/specificity/status/%d" % run.pk).json()
        self.assertTrue(state["finished"])
        self.assertEqual("finished", state["status"])

        genes = self.client.get("/specificity/download/%d/genes.csv" % run.pk)
        self.assertEqual("text/csv", genes["Content-Type"])
        lines = genes.content.decode().splitlines()
        self.assertTrue(lines[0].startswith("gene,genomes: hot,genomes: cold"))
        self.assertTrue(lines[1].startswith("geneA,4,0"))

        matrix = self.client.get("/specificity/download/%d/matrix.csv" % run.pk)
        rows = matrix.content.decode().splitlines()
        self.assertEqual("treatment", rows[1].split(",")[0])

    def test_a_change_to_the_mutations_discards_every_run(self):
        self.run_it()
        request_rebuild(self.experiment.id, reason="test")
        run_rebuilds(self.experiment.id)
        self.assertFalse(SpecificityRun.objects.exists())

    def test_a_run_discarded_while_it_ran_saves_nothing(self):
        run = util.new_run(self.experiment, settings.clean({}, ["cold", "hot"]), self.user)
        original = util.genomes_for

        def discarding(experiment_id, chosen):
            SpecificityRun.objects.filter(pk=run.pk).delete()
            return original(experiment_id, chosen)

        util.genomes_for = discarding
        try:
            tasks.run_specificity.enqueue(run.pk)
        finally:
            util.genomes_for = original
        self.assertFalse(SpecificityRun.objects.exists())

    def test_too_little_to_compare_is_an_answer_not_a_failure(self):
        self.run_it(treatments=["cold"])
        run = SpecificityRun.objects.get()
        self.assertEqual(STATUS_FINISHED, run.status)
        self.assertIn("two treatments", run.result["dice"]["skipped"])
        page = self.client.get(self.url())
        self.assertContains(page, "two treatments")


@override_settings(TASKS=DATABASE_TASKS)
class QueuedRunTestCase(SpecificityFixture):
    def launch(self):
        self.client.post("/specificity/?experiment_id=%d" % self.experiment.id,
                         {"treatments": ["hot", "cold"], "permutations": 100,
                          "gene_rule": settings.GENE_RULE_NOT_SYNONYMOUS})
        return SpecificityRun.objects.get()

    def test_a_queued_run_says_it_is_waiting_for_a_worker(self):
        run = self.launch()
        self.assertEqual(STATUS_QUEUED, run.status)
        page = self.client.get("/specificity/?experiment_id=%d" % self.experiment.id)
        self.assertContains(page, "Waiting for a worker")
        self.assertContains(page, "/jobs/%d/cancel" % run.job_id)

    def test_a_run_cancelled_before_it_starts_does_nothing(self):
        run = self.launch()
        response = self.client.post("/jobs/%d/cancel" % run.job_id)
        self.assertEqual(200, response.status_code)

        class Context:
            class task_result:
                id = run.task_result_id

        tasks.run_specificity.func(Context, run.pk)
        run.refresh_from_db()
        self.assertEqual(STATUS_CANCELLED, run.status)
        self.assertIsNone(run.result)

    def test_a_run_cancelled_while_it_runs_stops(self):
        run = self.launch()
        from evospec import stats

        original = stats.BATCH_SIZE
        stats.BATCH_SIZE = 10
        tasks.POLL_SECONDS, poll = 0, tasks.POLL_SECONDS
        Job.objects.filter(pk=run.job_id).update(cancel_requested_at=None)
        calls = []
        real_check = tasks.jobs.check_cancelled

        def cancel_after_first(queue_id, *args):
            calls.append(queue_id)
            if len(calls) > 1:
                raise tasks.jobs.JobCancelled("stop")
            return real_check(queue_id, *args)

        tasks.jobs.check_cancelled = cancel_after_first

        class Context:
            class task_result:
                id = run.task_result_id

        try:
            tasks.run_specificity.func(Context, run.pk)
        finally:
            tasks.jobs.check_cancelled = real_check
            stats.BATCH_SIZE = original
            tasks.POLL_SECONDS = poll
        run.refresh_from_db()
        self.assertEqual(STATUS_CANCELLED, run.status)
        self.assertGreater(run.progress, 0)
        self.assertIsNone(run.result)


class AnonymousStateTestCase(SpecificityFixture):
    def test_the_state_of_a_run_nobody_owns(self):
        from mutint_specificity.views import _run_state

        self.client.post("/specificity/?experiment_id=%d" % self.experiment.id,
                         {"permutations": 10})
        run = SpecificityRun.objects.get()
        state = _run_state(run, AnonymousUser())
        self.assertEqual("", state["cancel_url"])
