import os

from django.apps import AppConfig


class SpecificityConfig(AppConfig):
    """Treatment specificity of genome evolution: a page, its cache, and an example.

    The statistics are the `evospec` package's (github.com/barricklab/evospec); this app
    turns an experiment's samples into its input, runs it on a worker, and draws the answer.
    """

    name = 'mutint_specificity'

    def ready(self):
        from django.urls import include, re_path
        from mutint_common.about_registry import register_about_section
        from mutint_common.example_registry import register_example_dataset
        from mutint_common.nav_registry import EXPERIMENT_SECTION, register_nav_item
        from mutint_common.plugin_registry import register_plugin_urlpatterns
        from mutint_common.rebuild_registry import register_rebuilder
        from mutint_specificity import util
        from mutint_specificity.version import __version__

        register_plugin_urlpatterns([
            re_path(r'^specificity/', include('mutint_specificity.urls')),
        ])
        register_nav_item('Specificity', url_name='specificity', section=EXPERIMENT_SECTION)
        register_about_section(self, name='mutint-specificity', version=__version__,
                               template='about/sections/mutint_specificity.html')

        # A **deletion**, as mutint-phylogeny registers: a stored run answers one reader's
        # question about the mutations as they were, so when they change every run the
        # experiment has is thrown away rather than recomputed. See `util.discard_runs`.
        util.REBUILD_NAME = register_rebuilder(
            'mutint_specificity', util.discard_runs, label='Specificity analyses')

        # The temperature evolution experiment of Deatherage et al. 2017: thirty clones from
        # five temperature treatments, with REL1207 as the ancestor. See examples/tee/README.md.
        register_example_dataset(
            'mutint-specificity-example',
            os.path.join(os.path.dirname(__file__), 'examples', 'tee'),
            description='Thirty E. coli clones evolved at five temperatures (TEE, '
                        'Deatherage et al. 2017).',
            ancestor='REL1207')
