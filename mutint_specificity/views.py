"""The Specificity page, the status its poll reads, and the CSV downloads.

Shaped like mutint-phylogeny's page: the settings form posts, the view either finds a run
that already answers those settings or starts one, and redirects back to the GET, which
shows that run -- its answer, or how far along it is.

**Running is not gated on `can_edit_experiment`.** What a run writes is a cached answer to one
reader's question, which changes nobody else's view -- the test the suite applies ("is the
write shared?") and the reason mutint-phylogeny's build button is ungated. It does need a
signed-in reader, because it puts work on the queue.
"""

import csv
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

import mutint_sample.views.common
from mutint_common.logger import user_extra
from mutint_common.util import get_user_context
from mutint_experiment.models import Experiment
from mutint_experiment.permissions import can_view_project
from mutint_jobs import jobs as jobs_api

from mutint_specificity import params as settings
from mutint_specificity import present, tasks, util
from mutint_specificity.models import SpecificityRun

logger = logging.getLogger("mutint_specificity.views")

COMPONENT = "mutint-specificity"


def _page_url(experiment_id):
    return "/specificity/?experiment_id=%d" % experiment_id


def _forbidden(request, context):
    return render(request, "403.html", context, status=403)


def _run_state(run, user):
    """What the page and its poll say about a run: status, progress, and the job's view."""
    job = jobs_api.row(run.job, user=user) if run.job_id else None
    queue_status = (job or {}).get("status", "")
    return {
        "id": run.pk,
        "status": run.status,
        "finished": run.is_finished,
        "progress": run.progress,
        "total": run.total,
        "percent": int(100 * run.progress / run.total) if run.total else 0,
        # A row still queued whose job the queue has never started is the one state the page
        # must name, because it looks exactly like a slow start: no worker is running.
        "waiting_for_worker": run.status == "queued" and queue_status == "READY",
        "cancel_requested": bool(job and job["cancel_requested"]),
        "cancel_url": ("/jobs/%d/cancel" % run.job_id
                       if job and job["cancellable"] else ""),
        "log_url": (job or {}).get("log", ""),
        "error": run.error,
        "created_by": run.created_by.username if run.created_by_id else "",
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def specificity(request):
    context = get_user_context(request.user)
    try:
        experiment = mutint_sample.views.common.get_experiment(request)
    except Experiment.DoesNotExist:
        return mutint_sample.views.common.no_experiment_selected(
            request, context, logger, "specificity analysis")
    except ValueError:
        return _forbidden(request, context)

    util.ensure_current(experiment.id)
    treatments = util.available_treatments(experiment.id)
    error = ""

    if request.method == "POST":
        if not request.user.is_authenticated:
            return _forbidden(request, context)
        try:
            chosen = settings.clean(request.POST, treatments)
        except settings.SettingsError as refused:
            chosen = settings.remembered(request, experiment.id, treatments)
            error = str(refused)
        else:
            settings.remember(request, experiment.id, chosen)
            run = util.run_for(experiment.id, settings.selection_key(chosen))
            again = request.POST.get("again") == "1"
            if run is None or (again and run.is_finished):
                _start(request, experiment, chosen)
            return redirect(_page_url(experiment.id))
    else:
        chosen = settings.remembered(request, experiment.id, treatments)

    run = util.run_for(experiment.id, settings.selection_key(chosen))
    context.update(experiment.experiment_context())
    context.update({
        "experiment_id": experiment.id,
        "title": "%s Specificity" % experiment.name,
        "treatments": [{"label": t, "selected": not chosen["treatments"]
                        or t in chosen["treatments"]} for t in treatments],
        "settings": chosen,
        "excluded_genes_text": " ".join(chosen["excluded_genes"]),
        "gene_rules": settings.GENE_RULES,
        "max_permutations": settings.MAX_PERMUTATIONS,
        "error": error,
        "can_run": request.user.is_authenticated,
        "run": run,
        "state": _run_state(run, request.user) if run else None,
        "run_gene_rule": (dict(settings.GENE_RULES).get(run.params.get("gene_rule"), "")
                          if run else ""),
        "results": (present.present(run.result, experiment.id)
                    if run and run.status == "finished" and run.result else None),
    })
    return render(request, "specificity/page.html", context)


def _start(request, experiment, chosen):
    run = util.new_run(experiment, chosen, request.user)
    job = jobs_api.enqueue(
        tasks.run_specificity, run.pk,
        user=request.user,
        label="Specificity — %s" % experiment.name,
        component=COMPONENT,
        experiment=experiment,
        cancellable=True)
    # `update`, not `save`: under an immediate backend the task has already run and written
    # its answer to this row, which a `save` of the stale instance would overwrite.
    SpecificityRun.objects.filter(pk=run.pk).update(task_result_id=job.task_result_id,
                                                    job=job)
    logger.info("specificity run %s queued", run.pk, extra=user_extra(request))
    return run


def _readable_run(request, pk):
    run = get_object_or_404(SpecificityRun.objects.select_related("experiment__project", "job"),
                            pk=pk)
    if not can_view_project(request.user, run.experiment.project):
        return None
    return run


@require_GET
def status(request, pk):
    """The run's state as JSON, for the page's poll. 404 rather than 403 for a run the
    reader may not see, so the endpoint does not say which ids exist."""
    run = _readable_run(request, pk)
    if run is None:
        return JsonResponse({"error": "Unknown run."}, status=404)
    return JsonResponse(_run_state(run, request.user))


@require_GET
def download(request, pk, what):
    run = _readable_run(request, pk)
    if run is None or not run.result:
        return HttpResponse("Unknown run.", status=404, content_type="text/plain")
    rows = present.gene_table_rows(run.result) if what == "genes" else \
        present.matrix_rows(run.result)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="specificity-%d-%s.csv"' % (run.experiment_id, what))
    writer = csv.writer(response)
    for row in rows:
        writer.writerow(row)
    return response
