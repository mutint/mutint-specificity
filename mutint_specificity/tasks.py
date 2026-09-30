"""The analysis, on a worker.

**The argument is a primary key**, the queue's contract. A failure records itself on the row
and re-raises, so the queue's record says a worker tried; a cancellation is recorded and not
re-raised, because it is not a failure. Neither is an experiment with too little in it to
compare: evospec answers with a sentence saying which analysis it skipped and why, and that
answer is stored like any other.

**The row can vanish under the task.** Its experiment's mutations may change while it runs,
and `util.discard_runs` then deletes every run the experiment has, this one included. Every
write here is therefore an `update()` on the primary key, which writes nothing to a row that
is gone -- the answer about mutations that have since moved is simply dropped.
"""

import logging
import time

from django.tasks import task
from django.utils import timezone

from mutint_jobs import jobs

from mutint_specificity import util
from mutint_specificity.models import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_FINISHED,
    STATUS_RUNNING,
    SpecificityRun,
)

logger = logging.getLogger("mutint_specificity.tasks")

#: How often, at most, a running analysis writes its progress and asks whether it has been
#: cancelled. evospec reports every couple of thousand randomizations -- a few milliseconds --
#: and a query that often would cost more than the arithmetic.
POLL_SECONDS = 1.0


def _queue_id(context, run):
    """This task's own queue result id -- from the context, because the view writes the
    row's copy *after* `enqueue` returns, and an immediate backend runs the task inside it."""
    from_context = getattr(getattr(context, "task_result", None), "id", None)
    return str(from_context) if from_context else (run.task_result_id or "")


def _update(run_id, **fields):
    """Write to the row if it still exists. Answers whether it did."""
    return SpecificityRun.objects.filter(pk=run_id).update(**fields) > 0


@task(takes_context=True)
def run_specificity(context, run_id):
    from evospec import analyze

    run = SpecificityRun.objects.filter(pk=run_id).first()
    if run is None:
        logger.info("specificity run %s is gone; nothing to do", run_id)
        return None

    queue_id = _queue_id(context, run)
    if jobs.is_cancelled(queue_id):
        _update(run_id, status=STATUS_CANCELLED, finished_at=timezone.now())
        return None
    params = run.params
    _update(run_id, status=STATUS_RUNNING, started_at=timezone.now(), progress=0)

    last = [0.0]

    def progress(done, total):
        now = time.monotonic()
        if now - last[0] < POLL_SECONDS and done < total:
            return
        last[0] = now
        if not _update(run_id, progress=done, total=total):
            raise jobs.JobCancelled("the run was discarded")
        jobs.check_cancelled(queue_id)

    try:
        genomes, samples, left_out = util.genomes_for(run.experiment_id, params)
        result = analyze(genomes, permutations=params["permutations"], seed=params["seed"],
                         alpha=params["alpha"], pairwise=params["pairwise"],
                         control=params["control"] or None, progress=progress)
    except jobs.JobCancelled:
        _update(run_id, status=STATUS_CANCELLED, finished_at=timezone.now())
        logger.info("specificity run %s cancelled", run_id)
        return None
    except Exception as failure:
        _update(run_id, status=STATUS_FAILED, finished_at=timezone.now(),
                error="%s: %s" % (type(failure).__name__, failure))
        raise

    result["samples"] = samples
    result["left_out"] = left_out
    if not _update(run_id, status=STATUS_FINISHED, finished_at=timezone.now(), result=result,
                   progress=run.total if run.total else 0):
        logger.info("specificity run %s was discarded while it ran", run_id)
        return None
    util.evict(run.experiment_id)
    return None
