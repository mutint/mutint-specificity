"""The settings of one analysis: what a reader may choose, what it is normalized to, and
where the reader's last choice is remembered.

The settings are the analysis's **own rules**, deliberately not the reader's view filter --
the same posture mutint-phylogeny takes, and for a related reason: a specificity analysis is
a statement about which genes evolution hit, and the frequency cutoff the reader uses for
reading a table is not part of that question. What would be -- which mutations count as a
gene hit, and which genes to leave out -- is chosen here, on the page, and stated beside the
answer.

## The session traps

`mutint_phylogeny.selection` lists them, and they are all `mutint_filter.view_filter`'s: the
session is JSON (no sets), integer keys come back as strings (every key here is `str()`), and
a nested dict mutated in place is not saved (`remember` reassigns the whole thing).
"""

import hashlib
import json
import re

SESSION_KEY = "mutint_specificity_settings"
MAX_REMEMBERED_EXPERIMENTS = 20

#: Which mutations assigned to one gene count as a hit on it. The default is the analysis's
#: original rule: a synonymous SNP changes no protein, so it says nothing about selection.
GENE_RULE_NOT_SYNONYMOUS = "not_synonymous"
GENE_RULE_ALL = "all"
GENE_RULE_NONSYNONYMOUS = "nonsynonymous"
GENE_RULES = [
    (GENE_RULE_NOT_SYNONYMOUS, "Every mutation except synonymous SNPs"),
    (GENE_RULE_ALL, "Every mutation, synonymous SNPs included"),
    (GENE_RULE_NONSYNONYMOUS, "Only nonsynonymous and nonsense SNPs"),
]

DEFAULT_PERMUTATIONS = 10000
#: The paper ran a million; more than that is a typo rather than a question.
MAX_PERMUTATIONS = 1000000
DEFAULT_ALPHA = 0.05

DEFAULTS = {
    "treatments": [],
    "clones_only": False,
    "gene_rule": GENE_RULE_NOT_SYNONYMOUS,
    "excluded_genes": [],
    "control": "",
    "pairwise": True,
    "permutations": DEFAULT_PERMUTATIONS,
    "seed": 0,
    "alpha": DEFAULT_ALPHA,
}

GENE_SEPARATOR = re.compile(r"[\s,;]+")


class SettingsError(ValueError):
    """A setting a reader chose that cannot be run, with a sentence saying which."""


def _flag(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _number(value, kind, name, low, high):
    try:
        number = kind(str(value).strip())
    except (TypeError, ValueError):
        raise SettingsError("%s must be a number." % name)
    if not (low <= number <= high):
        raise SettingsError("%s must be between %s and %s." % (name, low, high))
    return number


def clean(raw, available_treatments):
    """Normalized settings from a POST (a QueryDict) or a stored dict.

    `available_treatments` is the list of treatment labels the experiment's samples carry;
    a treatment that is not among them is dropped rather than refused, because a stored
    choice may name a label that has since been renamed away. Raises `SettingsError`.
    """
    posted = hasattr(raw, "getlist")

    def get(name):
        if posted and name == "treatments":
            return raw.getlist(name)
        if posted and isinstance(DEFAULTS[name], bool):
            return raw.get(name, "")   # an unticked checkbox is absent from a POST
        return raw.get(name, DEFAULTS[name])

    treatments = get("treatments") or []
    if isinstance(treatments, str):
        treatments = [treatments]
    live = list(available_treatments)
    treatments = [t for t in live if t in set(treatments)]
    if len(treatments) == len(live):
        treatments = []   # every treatment is the same question as no narrowing

    gene_rule = get("gene_rule") or GENE_RULE_NOT_SYNONYMOUS
    if gene_rule not in dict(GENE_RULES):
        raise SettingsError("Unknown rule for counting gene hits: %s." % gene_rule)

    excluded = get("excluded_genes") or []
    if isinstance(excluded, str):
        excluded = GENE_SEPARATOR.split(excluded)
    excluded = sorted({gene.strip() for gene in excluded if gene and gene.strip()})

    control = (get("control") or "").strip()
    in_play = treatments or live
    if control and control not in in_play:
        raise SettingsError("The control treatment, %s, is not one of the treatments analyzed."
                            % control)

    return {
        "treatments": treatments,
        "clones_only": _flag(get("clones_only")),
        "gene_rule": gene_rule,
        "excluded_genes": excluded,
        "control": control,
        "pairwise": _flag(get("pairwise")),
        "permutations": _number(get("permutations"), int, "Randomizations", 0,
                                MAX_PERMUTATIONS),
        "seed": _number(get("seed"), int, "The random seed", 0, 2 ** 32 - 1),
        "alpha": _number(get("alpha"), float, "The significance level", 0.0, 1.0),
    }


def selection_key(params):
    """The canonical identity of the question a run answers."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def remembered(request, experiment_id, available_treatments):
    """This reader's last settings on this experiment, or the defaults.

    A stored choice that no longer cleans -- a control treatment renamed away -- falls back
    to the defaults rather than failing the page.
    """
    stored = (request.session.get(SESSION_KEY) or {}).get(str(experiment_id))
    if stored:
        try:
            return clean(stored, available_treatments)
        except SettingsError:
            pass
    return clean(DEFAULTS, available_treatments)


def remember(request, experiment_id, params):
    stored = dict(request.session.get(SESSION_KEY) or {})
    stored.pop(str(experiment_id), None)
    stored[str(experiment_id)] = params
    while len(stored) > MAX_REMEMBERED_EXPERIMENTS:
        stored.pop(next(iter(stored)))
    request.session[SESSION_KEY] = stored
