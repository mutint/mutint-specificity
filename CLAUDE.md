# CLAUDE.md — mutint-specificity

Guidance for Claude Code working in this repository.

It is a **submodule of `mutint`**. Edit it **here**, in the suite-root checkout, never in
`mutint/mutint-specificity`. That copy is on a detached HEAD, and a commit made there is
reachable only by SHA inside that one clone. See the suite `CLAUDE.md`.

---

## What this is

The **Specificity** page: whether genome evolution was specific to the treatment each
population evolved under, by the analysis of Deatherage *et al.* 2017. The statistics are the
**evospec** package's (`github.com/barricklab/evospec`, the successor to
`breseq-ext-specificity`), pinned by SHA in `requirements.txt`. This app does three things
with it:

- turns an experiment's samples into evospec's input;
- runs `evospec.analyze` on a worker;
- draws the answer.

**A sample is a genome when it has a treatment** (`Sample.treatment`). A mutation counts
towards a gene when the annotator's `single_gene_affected` names one. Deliberately, it does not
count by evospec's own GenBank-and-promoter assignment. Two consequences are worth stating on
the page and in the docs, and both are:

- a promoter is breseq's 150 bases, not a setting;
- repeat regions are not set aside.

---

## The pieces

| file | what |
|---|---|
| `params.py` | The settings a reader chooses, normalized (`clean`), hashed (`selection_key`) and remembered per experiment in the session. |
| `util.py` | `genomes_for` (samples and calls to `evospec.Genome`s), and the cache: `discard_runs` (the rebuilder), `ensure_current`, `new_run`, `evict`. |
| `models.py` | `SpecificityRun`: one reader's settings, the job computing them, and the answer as JSON. |
| `tasks.py` | `run_specificity`, the cancellable task. |
| `present.py` | evospec's dicts lined up for the templates, and the two CSV downloads. |
| `views.py` | The page (GET shows, POST starts or reuses a run), the status the page polls, and the downloads. |
| `examples/tee/` | The thermal tolerance experiment: 31 `.gd`, REL606 as GFF3, a `metadata.csv`, and a README with the expected answer. |

---

## Things that are load-bearing

- **A run is a cache keyed by one reader's question**, as in mutint-phylogeny. The rebuilder
  it registers is a *deletion*: when the experiment's mutations change, every run is thrown
  away. `ensure_current` on the page turns a mark-without-run (a sample renumber) into that
  discard before anything is read.
- **The row can vanish under the task.** Every write in `tasks.py` is an `update()` by primary
  key, so a run discarded mid-computation saves nothing. The progress callback raising on a
  vanished row is also what stops the computation early.
- **The view writes `task_result_id` and `job` with `update()`, not `save()`.** Under an
  immediate backend the task has already finished inside `enqueue`. A `save()` of the stale
  instance would write `queued` back over the answer.
- **Cancelling polls at most once a second** (`POLL_SECONDS`). evospec calls back every
  couple of thousand randomizations, which is milliseconds apart.
- **Running needs a signed-in reader but not write access.** What a run writes is a cache of
  one reader's question, which is the test the suite applies to mutint-phylogeny's build
  button. Reading a stored answer needs only view access, as the page does.
- **Too little to compare is an answer, not a failure.** evospec returns a sentence (`skipped`)
  for a Dice test with fewer than two treatments, and the page shows it.
- **The example's ancestor is designated by `load_example`**, through the registry's
  `ancestor=` (core). Without it every analysis would count REL1207's mutations as evolution.
- **The migration depends on `__first__`** of `mutint_experiment` and `mutint_jobs`.
  `makemigrations` rewrites these to concrete names every time, and core's `test_migrations`
  fails on a cross-component dependency that names a file. Put them back by hand.

## What it deliberately does not do

- **Apply the reader's view filter.** The page states its own rules with `own_rules=`, as
  mutint-phylogeny does. A frequency cutoff for reading a table is not part of the question of
  which genes evolution hit.
- **Store anything shared.** There is no export type and no derived data of record.
- **Assign genes itself.** That is the annotator's answer, and a second opinion here would
  disagree with the Mutations page about what a mutation hits.

---

## Tests

```bash
cd mutint && ./mutint test mutint_specificity
```

Uncommitted edits, from the assembled project:
`PYTHONPATH=/path/to/mutint-code/mutint-specificity ./mutint test mutint_specificity`.

Before it is a submodule, or from mutint-core, use a settings module that adds the app:

```bash
cd mutint-core
cat > /tmp/specificity_settings.py <<'PY'
from config.settings_local import *  # noqa: F401,F403
INSTALLED_APPS = INSTALLED_APPS + ["mutint_specificity"]
PY
env/main/bin/pip install -e /path/to/evospec
DJANGO_SETTINGS_MODULE=specificity_settings PYTHONPATH=/tmp:../mutint-specificity ./mutint test mutint_specificity
```

**38 tests.** `test_example` loads the real dataset against REL606. The queued-run tests switch
`TASKS` to the database backend, so a launch queues instead of finishing.
