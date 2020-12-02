"""
Stage to transform arrays with weights into actual `histograms`
that represent event counts
"""

from __future__ import absolute_import, print_function, division

import numpy as np

from pisa import FTYPE
from pisa.core.stage import Stage
from pisa.core.translation import histogram
from pisa.core.binning import MultiDimBinning
from pisa.utils.profiler import profile
from pisa.utils import vectorizer


class hist(Stage):  # pylint: disable=invalid-name
    """stage to histogram events"""
    def __init__(
        self,
        **std_kwargs,
        ):

        # init base class
        super().__init__(
            expected_params=(),
            **std_kwargs,
        )




    def setup_function(self):

        assert isinstance(self.apply_mode, MultiDimBinning), "Hist stage needs a binning as `apply_mode`, but is %s"%self.apply_mode

        if isinstance(self.calc_mode, MultiDimBinning):

            # The two binning must be exclusive
            assert len(set(self.calc_mode.names) & set(self.apply_mode.names)) == 0

            self.transform_binning = self.calc_mode + self.apply_mode

            # go to "events" mode to create the transforms

            for container in self.data:
                self.data.representation = "events"

                sample = [container[name] for name in self.transform_binning.names]
                hist = histogram(sample, None, self.transform_binning, averaged=False)

                self.data.representation = self.transform_binning

                container['hist_transform'] = hist

    def apply_function(self):

        #if self.calc_mode == 'binned':
        #    raise NotImplementedError('Needs some care, broken in pisa4')
        #    self.data.representation = self.apply_mode
        #    for container in self.data:
        #        # calcualte errors
        #        if self.error_method in ['sumw2']:
        #            vectorizer.pow(
        #                vals=container['weights'],
        #                pwr=2,
        #                out=container['weights_squared'],
        #            )
        #            vectorizer.sqrt(
        #                vals=container['weights_squared'], out=container['errors']
        #            )

        if isinstance(self.calc_mode, MultiDimBinning):

            #axes=((0,), (0,))

            for container in self.data:

                container.representation = self.calc_mode
                weights = container['weights']

                self.data.representation = self.transform_binning
                transform = container['hist_transform']

                transform = transform.reshape(weights.shape[0], -1)

                #hist = np.tensordot(transform, weights, axes=axes)
                hist = weights @ transform
                if self.error_method == 'sumw2':
                    #sumw2 = np.tensordot(transform, np.square(weights), axes=axes)
                    sumw2 = np.square(weights) @ transform

                container.representation = self.apply_mode

                container['weights'] = hist

                if self.error_method == 'sumw2':
                    container['errors'] = np.sqrt(sumw2)

        elif self.calc_mode == 'events':
            for container in self.data:
                # calcualte errors

                container.representation = self.calc_mode
                sample = [container[name] for name in self.apply_mode.names]
                weights = container['weights']

                hist = histogram(sample, weights, self.apply_mode, averaged=False)

                if self.error_method == 'sumw2':
                    sumw2 = histogram(sample, np.square(weights), self.apply_mode, averaged=False)

                container.representation = self.apply_mode
                
                container['weights'] = hist

                if self.error_method == 'sumw2':
                    container['errors'] = np.sqrt(sumw2)