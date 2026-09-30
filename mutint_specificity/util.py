"""What the analysis is run on, and the cache of what it answered.

`genomes_for` turns one experiment's samples into `evospec.Genome`s: each sample with a
treatment is a genome, each mutation observed in it is a `Mutation`, and the gene a mutation
is assigned to is the annotator's `single_gene_affected` -- MutInt's own answer to "does this
mutation name exactly one gene" (see **breseq's gene lists are columns, not data** in
mutint-core's CLAUDE.md). That replaces the GenBank-and-promoter assignment evospec's command
line does, and it differs from it in two ways worth saying wherever the answer is shown: a
promoter counts within breseq's 150 bases of one gene's start, and repeat regions are not
set aside.
"""

import logging

from django.db import transaction

from mutint_sample.functional_change import functional_change_bucket
from mutint_sample.util import calls_for_samples, get_ordered_sample_dict

from mutint_specificity import params as settings
from mutint_specificity.models import UNFINISHED_STATUSES, SpecificityRun

logger = logging.getLogger("mutint_specificity.util")

#: The name `register_rebuilder` answered with, set in apps.py.
REBUILD_NAME = None

#: Finished runs kept per experiment, newest first -- mutint-phylogeny's number, for its
#: reason: a reader trying settings should find the last few again, and the table is a cache.
MAX_RUNS_PER_EXPERIMENT = 8

NOT_A_HIT = {
    settings.GENE_RULE_NOT_SYNONYMOUS: lambda bucket: bucket == "synonymous",
    settings.GENE_RULE_ALL: lambda bucket: False,
    settings.GENE_RULE_NONSYNONYMOUS: lambda bucket: bucket not in ("nonsynonymous",
                                                                     "nonsense"),
}

_GD = "mutation__supplemental_data__mutint_core__genome_diff__"


def available_treatments(experiment_id):
    """The treatment labels the experiment's samples carry, the ancestor aside, in the
    order every treatment picker lists them."""
    from mutint_sample.views.common import get_treatment_names
    return get_treatment_names(experiment_id)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def genomes_for(experiment_id, params):
    """`(genomes, samples, left_out)` for these settings.

    `genomes` is the `evospec.Genome` list, in the experiment's sample order; `samples` maps
    each genome's name to its sample's id, for links; `left_out` lists the samples that were
    not analyzed and why, so the page can say so rather than silently answering about fewer
    samples than the reader expects. A sample outside the chosen treatments is not "left
    out" -- the reader asked for that.
    """
    from evospec import Genome, Mutation

    chosen = set(params["treatments"])
    excluded_genes = set(params["excluded_genes"])
    not_a_hit = NOT_A_HIT[params["gene_rule"]]

    included = []
    left_out = []
    for sample in get_ordered_sample_dict(experiment_id).values():
        if not sample.treatment:
            left_out.append({"sample": sample.label, "sample_id": sample.id,
                             "reason": "no treatment"})
        elif chosen and sample.treatment not in chosen:
            continue
        elif params["clones_only"] and sample.is_mixed:
            left_out.append({"sample": sample.label, "sample_id": sample.id,
                             "reason": "population sample"})
        else:
            included.append(sample)

    mutations = {sample.id: [] for sample in included}
    rows = (calls_for_samples(list(mutations), experiment_id)
            .filter(present=True)
            .values_list("sample_id", "mutation__mutation_type", "mutation__snp_type",
                         "mutation__annotation__single_gene_affected",
                         _GD + "size", _GD + "repeat_name")
            .order_by("sample_id", "mutation__seq_id", "mutation__start_position")
            .iterator(chunk_size=2000))
    for sample_id, kind, snp_type, gene, size, repeat_name in rows:
        bucket = functional_change_bucket(snp_type) if kind == "SNP" else None
        if gene is not None and (not_a_hit(bucket or "") or gene in excluded_genes):
            gene = None
        mutations[sample_id].append(Mutation(
            kind, gene or None, bucket,
            _int(size) if kind in ("DEL", "AMP") else None,
            repeat_name if kind == "MOB" else None))

    genomes = []
    samples = {}
    seen = set()
    for sample in included:
        name = sample.label
        if name in seen:   # evospec needs unique names; two samples may share a label
            name = "%s (#%d)" % (name, sample.id)
        seen.add(name)
        samples[name] = sample.id
        genomes.append(Genome(name, sample.treatment, tuple(mutations[sample.id])))
    return genomes, samples, left_out


# --- the cache ------------------------------------------------------------------------------

def discard_runs(experiment_id):
    """The rebuilder: every run this experiment has is about mutations that have moved.

    A run still going is deleted too; its task finds its row gone when it comes to save and
    drops the answer. Deleting is the whole of "rebuilding" a cache.
    """
    SpecificityRun.objects.filter(experiment_id=experiment_id).delete()


def ensure_current(experiment_id):
    """Discard now if something marked this experiment stale without running its rebuilds.

    `mutint_experiment/samples.py` marks on a sample renumber and runs nothing, so this is
    what turns that mark into a discard before anything is read -- mutint-phylogeny's
    `ensure_current`, for the same reason.
    """
    if not REBUILD_NAME:
        return
    from mutint_common.rebuild_registry import ensure_fresh
    ensure_fresh(REBUILD_NAME, experiment_id)


def run_for(experiment_id, key):
    return (SpecificityRun.objects.filter(experiment_id=experiment_id, selection_key=key)
            .select_related("job").first())


def evict(experiment_id):
    """Keep the newest `MAX_RUNS_PER_EXPERIMENT` finished runs; never touch an unfinished
    one, which a worker may be about to save into."""
    finished = (SpecificityRun.objects.filter(experiment_id=experiment_id)
                .exclude(status__in=UNFINISHED_STATUSES)
                .order_by("-created_at").values_list("pk", flat=True))
    stale = list(finished[MAX_RUNS_PER_EXPERIMENT:])
    if stale:
        SpecificityRun.objects.filter(pk__in=stale).delete()


@transaction.atomic
def new_run(experiment, params, user):
    """A fresh queued row for these settings, replacing any finished one with the same key."""
    key = settings.selection_key(params)
    SpecificityRun.objects.filter(experiment=experiment, selection_key=key).delete()
    return SpecificityRun.objects.create(
        experiment=experiment, selection_key=key, params=params,
        created_by=user if user.is_authenticated else None,
        total=params["permutations"])
