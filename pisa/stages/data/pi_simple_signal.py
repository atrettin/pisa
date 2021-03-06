"""
Stage to generate simple 1D data consisting 
of a flat background + gaussian peak with a mean and a width

"""
from __future__ import absolute_import, print_function, division

__author__ = "Etienne Bourbeau (etienne.bourbeau@icecube.wisc.edu)"

import numpy as np
from pisa import FTYPE
from pisa.core.container import Container
from pisa.core.pi_stage import PiStage

# Load the modified index lookup function
from pisa.core.bin_indexing import lookup_indices


class pi_simple_signal(PiStage):
    """
    random toy event generator PISA Pi class

    Parameters
    ----------
    data
    params
        Expected params .. ::

            n_events : int
                Number of events to be generated per output name
            random
            seed : int
                Seed to be used for random

    input_names
    output_names
    debug_mode
    input_specs
    calc_specs
    output_specs

    """

    def __init__(
        self,
        data=None,
        params=None,
        input_names=None,
        output_names=None,
        debug_mode=None,
        input_specs=None,
        calc_specs=None,
        output_specs=None,
    ):
        expected_params = (  # parameters fixed during fit
            'n_events_data',
            'stats_factor',
            'signal_fraction',

            # minimum + maximum bkg values
            'bkg_min',
            'bkg_max',

            # fitted parameters
            'mu',
            'sigma')

        # what keys are added or altered for the outputs during apply
        output_apply_keys = ('weights','errors')

        # init base class
        super().__init__(
            data=data,
            params=params,
            expected_params=expected_params,
            input_names=input_names,
            output_names=output_names,
            debug_mode=debug_mode,
            input_specs=input_specs,
            calc_specs=calc_specs,
            output_specs=output_specs,
            output_apply_keys=output_apply_keys
        )

        # doesn't calculate anything
        assert self.calc_mode is None

    def setup_function(self):
        '''
        This is where we figure out how many events to generate,
        define their weights relative to the data statistics
        and initialize the container we will need

        This function is run once when we instantiate the pipeline
        '''

        #
        # figure out how many signal and background events to create
        #
        n_data_events = int(self.params.n_events_data.value.m)
        self.stats_factor = float(self.params.stats_factor.value.m)
        signal_fraction = float(self.params.signal_fraction.value.m)

        # Number of simulated MC events
        self.n_mc = int(n_data_events*self.stats_factor)
        # Number of signal MC events
        self.nsig = int(self.n_mc*signal_fraction)
        self.nbkg = self.n_mc-self.nsig                     # Number of bkg MC events

        # Go in events mode
        self.data.data_specs = 'events'

        #
        # Create a signal container, with equal weights
        #
        signal_container = Container('signal')
        signal_container.data_specs = 'events'
        # Populate the signal physics quantity over a uniform range
        signal_initial  = np.random.uniform(low=self.params.bkg_min.value.m,
                                               high=self.params.bkg_max.value.m,
                                               size=self.nsig)

        signal_container.add_array_data('stuff', signal_initial)
        # Populate its MC weight by equal constant factors
        signal_container.add_array_data('weights', np.ones(self.nsig, dtype=FTYPE)*1./self.stats_factor)
        # Populate the error on those weights
        signal_container.add_array_data('errors',(np.ones(self.nsig, dtype=FTYPE)*1./self.stats_factor)**2. )

        #
        # Compute the bin indices associated with each event
        #
        sig_indices = lookup_indices(sample=[signal_container['stuff']], binning=self.output_specs)
        sig_indices = sig_indices.get('host')
        signal_container.add_array_data('bin_indices', sig_indices)

        #
        # Compute an associated bin mask for each output bin
        #
        for bin_i in range(self.output_specs.tot_num_bins):
            sig_bin_mask = sig_indices == bin_i
            signal_container.add_array_data(key='bin_{}_mask'.format(bin_i), data=sig_bin_mask)

        #
        # Add container to the data
        #
        self.data.add_container(signal_container)

        #
        # Create a background container
        #
        if self.nbkg > 0:

            bkg_container = Container('background')
            bkg_container.data_specs = 'events'
            # Create a set of background events
            initial_bkg_events = np.random.uniform(low=self.params.bkg_min.value.m, high=self.params.bkg_max.value.m, size=self.nbkg)
            bkg_container.add_array_data('stuff', initial_bkg_events)
            # create their associated weights
            bkg_container.add_array_data('weights', np.ones(self.nbkg)*1./self.stats_factor)
            bkg_container.add_array_data('errors',(np.ones(self.nbkg)*1./self.stats_factor)**2. )
            # compute their bin indices
            bkg_indices = lookup_indices(sample=[bkg_container['stuff']], binning=self.output_specs)
            bkg_indices = bkg_indices.get('host')
            bkg_container.add_array_data('bin_indices', bkg_indices)
            # Add bin indices mask (used in generalized poisson llh)
            for bin_i in range(self.output_specs.tot_num_bins):
                bkg_bin_mask = bkg_indices==bin_i
                bkg_container.add_array_data(key='bin_{}_mask'.format(bin_i), data=bkg_bin_mask)

            self.data.add_container(bkg_container)


        #
        # Add the binned counterpart of each events container
        #
        for container in self.data:
            container.array_to_binned('weights', binning=self.output_specs, averaged=False)
            container.array_to_binned('errors', binning=self.output_specs, averaged=False)


    def apply_function(self):
        '''
        This is where we re-weight the signal container
        based on a model gaussian with tunable parameters
        mu and sigma.

        The background is left untouched in this step.

        A possible upgrade to this function would be to make a 
        small background re-weighting

        This function will be called at every iteration of the minimizer
        '''

        #
        # Make sure we are in events mode
        #
        self.data.data_specs = 'events'
        from scipy.stats import norm

        for container in self.data:

            if container.name == 'signal':
                #
                # Signal is a gaussian pdf, weighted to account for the MC statistics and the signal fraction
                #
                reweighting = norm.pdf(container['stuff'].get('host'), loc=self.params['mu'].value.m, scale=self.params['sigma'].value.m)/self.stats_factor
                reweighting/=np.sum(reweighting)
                reweighting*=(self.nsig/self.stats_factor)

                reweighting[np.isnan(reweighting)] = 0.

                #
                # New MC errors = MCweights squared
                #
                new_errors = reweighting**2.

                #
                # Replace the weight information in the signal container
                #
                np.copyto(src=reweighting, dst=container["weights"].get('host'))
                np.copyto(src=new_errors, dst=container['errors'].get('host'))
                container['weights'].mark_changed()
                container['errors'].mark_changed()

                # Re-bin the events weight into new histograms
                container.array_to_binned('weights', binning=self.output_specs, averaged=False)
                container.array_to_binned('errors', binning=self.output_specs, averaged=False)
