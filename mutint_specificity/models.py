"""One specificity analysis: the settings a reader chose, and what came back.

**A cache, not data of record** -- the shape mutint-phylogeny's `PhylogeneticTree` settled.
The settings (which treatments, which mutations count as a gene hit, how many
randomizations) are one reader's question, so a row is keyed by that question
(`selection_key`) rather than by the experiment alone, and every row an experiment has is
thrown away when its mutations change (`util.discard_runs`, registered as its rebuilder).
There is a current answer to a question, or there is none, and "none" is the page before
anybody pressed Run.

A row exists before its answer does, because the answer is computed on a worker: `status`
is what the task last wrote, and `job` is how to ask the queue -- the two disagree in the
one useful way, a row still `queued` whose job the queue has never started, which means no
worker is running.
"""

from django.contrib.auth.models import User
from django.db import models

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_FINISHED = "finished"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

STATUS_CHOICES = [
    (STATUS_QUEUED, "Queued"),
    (STATUS_RUNNING, "Running"),
    (STATUS_FINISHED, "Finished"),
    (STATUS_FAILED, "Failed"),
    (STATUS_CANCELLED, "Cancelled"),
]

UNFINISHED_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)


class SpecificityRun(models.Model):
    experiment = models.ForeignKey("mutint_experiment.Experiment", on_delete=models.CASCADE,
                                   related_name="specificity_runs")
    #: sha256 of the canonical settings; see `params.selection_key`.
    selection_key = models.CharField(max_length=64, db_index=True)
    #: The settings themselves, normalized by `params.clean`.
    params = models.JSONField(default=dict)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    task_result_id = models.CharField(max_length=64, blank=True, default="")
    # SET_NULL: the job's row may be reaped by `./mutint reap_jobs` long after the answer is
    # worth keeping.
    job = models.ForeignKey("mutint_jobs.Job", null=True, blank=True,
                            on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    #: Randomizations done, out of `total`, while the Dice test runs.
    progress = models.BigIntegerField(default=0)
    total = models.BigIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    #: `evospec.analyze`'s answer, plus the samples it was asked about -- see `tasks`.
    result = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def is_finished(self):
        return self.status not in UNFINISHED_STATUSES

    def __str__(self):
        return "Specificity run %s (%s)" % (self.pk, self.status)
