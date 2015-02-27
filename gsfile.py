# -*- coding: utf-8 -*-
"""
Created on Fri Feb 28 10:05:07 2014

Created while working for the US Geological Survey

@author: brent lunghino
"""
import os
import csv

import matplotlib
import numpy as np
from matplotlib import cm, pyplot as plt
from scipy.stats import nanmean

import pandas as pd


class BaseGSFile:
    """
    base class to store and manipulate grain size data

    when initialized, reads in data from a uniform format csv file stored in
    csv_directory

    layers can be classified according to layer_type_lookup
    """
    ## allows layer classifications to be specified by subclassing
    layer_type_lookup = {
                        -1: 'Post-tsunami',
                         0: 'Pre-tsunami',
                         1: 'Suspension graded',
                         2: 'Inverse graded',
                         3: 'Normal graded',
                         4: 'Massive',
                         5: 'Not classified',
                         6: 'Not suspension graded',
                         7: 'Mud',
                         8: 'Mud cap',
                         9: 'Unknown',
                    }
    ## allows a directory to be specified by subclassing
    project_directory = ''
    ## allows mm/pixel ratio to be specified by subclassing
    mm_pix = None

    def __init__(
              self,
              csv_file_location='',
              csv_directory='',
              mm_pix=None,
              layer_type_lookup=None,
              metadata_rows=17,
              col_header_rows=6,
              numeric_fields=('Min Depth', 'Max Depth', 'Layer Type', 'Layer'),
              read_other=False
              ):
        """
        csv_file_name is the name of the csv file
        (can be full path or configure get_csv_file_path)

        metadata_rows is the number of rows in the csv file before the start
        of the grain size distribution data

        col_header_rows is the number of rows in the csv file that contain
        metadata specific to each sample in the csv file.
        These rows must come between the trench scale metadata and the
        grain size distribution

        mm_pix is the mm per pixel conversion factor
        """
        ## allows settings to be overridden when the object is initiated
        if not read_other:
            if csv_directory:
                self.project_directory = project_directory
            if mm_pix:
                self.mm_pix = mm_pix
            if layer_type_lookup:
                self.layer_type_lookup = layer_type_lookup
            ## get the full file path for the csv file
            self.csv_file_path = self.get_csv_file_path(csv_file_location)
            self.gsfileuniform = os.path.split(self.csv_file_path)[1]
            with open(self.csv_file_path, 'r') as csvfile:
                rdr = csv.reader(csvfile, dialect='excel', strict=True,
                                skipinitialspace=True)
                ## sequence of lists where each list is a row from the csv file
                lines = [line for line in rdr]
            ## parse csv file contents by row
            for ii, m in enumerate(lines[:metadata_rows]):
                if m[0]:
                    ## values for numeric fields are converted to numpy arrays
                    if m[0] in numeric_fields:
                        att = np.asarray([x if x != '' else "nan" for x in m[1:]],
                                        dtype=np.float64)
                    ## values for non numeric fields are kept as lists
                    else:
                        att = m[1:]
                    ## first group of meta data store a single value associated
                    ## with the entire file
                    if ii < metadata_rows - col_header_rows -1:
                        setattr(self, m[0].replace(' ','_').lower(), att[0])
                    ## second group of meta data rows stores a sequence of values
                    ## with one value for each grain size sample (col_header_rows)
                    elif len(att) > 0:
                        setattr(self, m[0].replace(' ','_').lower(), att)
                    ## when no data exists in a col_header_row setattr to None
                    else:
                        setattr(self, m[0].replace(' ','_').lower(), None)
            ## get strings values for layer type codes
            self.layer_type_strings = [self.layer_type_lookup[x] for x in self.layer_type]
            ## get data into numpy array
            temp = np.asarray(lines[metadata_rows:], dtype=np.float64)
            self.bins = temp[:,0]
            self.bins_phi = self._convert_bins_to_phi()
            self.bins_phi_mid = self._convert_bins_to_phi_mid()
            self.dists = temp[:,1:]
            self.mid_depth = (self.min_depth+self.max_depth) / 2

    def get_csv_file_path(self, csv_file_location):
        """return the full path to the csv file"""
        return self.project_directory + csv_file_location

    def _convert_bins_to_phi(self):
        """
        internal method to convert bins to phi units
        """
        if self.bin_units == 'phi':
            return self.bins
        ## mid point between phi bin edges (used for statistics)
        elif self.bin_units == 'phi mid':
            return None
        ## settling velocity
        elif self.bin_units == 'psi':
            return None
        elif self.bin_units == 'mm':
            return -np.log2(self.bins)
        elif self.bin_units == 'pixels' and self.mm_pix is not None:
            return -np.log2(self.bins*self.mm_pix)
        else:
            return None

    def _convert_bins_to_phi_mid(self):
        """
        internal method to convert bins to phi midpoints
        """
        if self.bin_units == 'phi mid':
            return self.bins
        elif self.bins_phi is not None:
            mpt1 = np.asarray(self.bins_phi[0] + 0.5*(self.bins_phi[0]-self.bins_phi[1]))
            bins_phi_mid = self.bins_phi[1:] + 0.5*(self.bins_phi[:-1]-self.bins_phi[1:])
            return np.hstack((mpt1, bins_phi_mid))
        else:
            return None


class GSFile(BaseGSFile):
    """
    BaseGSFile subclass with methods to calculate statistics and make plots

    stats calculated using formulations in sedstats.m by Bruce Jaffe 10/2/03
    formulas originally from sedsize version 3.3 documentation (7/12/89)
    """
    def dist_means(self):
        """
        calculate the mean of each distribution
        """
        means = np.zeros_like(self.mid_depth)
        for ii, dist in enumerate(self.dists.T):
            means[ii] = np.sum(dist*self.bins_phi_mid) / dist.sum()
        return means

    def dist_devs(self):
        """
        returns deviation from the mean and the mean
        """
        means = self.dist_means()
        devs = np.zeros_like(self.dists)
        for ii, m in enumerate(means):
            devs[:,ii] = self.bins_phi_mid - m
        return devs, means

    def dist_stds(self):
        """
        calculate the standard deviation of each distribution
        """
        devs = self.dist_devs()[0]
        variances = np.zeros_like(self.mid_depth)
        for ii, dist in enumerate(self.dists.T):
            variances[ii] = np.sum(dist*devs[:,ii]**2) / dist.sum()
        return np.sqrt(variances)

    def dist_moments(self):
        """
        calculate 1st through 4th moments for each distribution
        """
        devs, m1 = self.dist_devs()
        m2 = np.zeros_like(self.mid_depth)
        m3 = np.zeros_like(self.mid_depth)
        m4 = np.zeros_like(self.mid_depth)
        for ii, dist in enumerate(self.dists.T):
            dist_sum = dist.sum()
            m2[ii] = np.sum(dist*devs[:,ii]**2) / dist_sum
            std = np.sqrt(m2[ii])
            m3[ii] = np.sum(dist*(devs[:,ii]/std)**3) / dist_sum
            m4[ii] = np.sum(dist*(devs[:,ii]/std)**4) / dist_sum
        return m1, m2, m3, m4

    def bulk_dist(self):
        """
        calculate bulk distribution for all samples of tsunami
        sediments in trench
        """
        if not np.isnan(self.min_depth).any() and len(self.sample_id) > 1:
            dists = self.dists[:,self.layer > 0]
            diffs = [x - self.min_depth[ii] for ii, x in enumerate(self.max_depth)]
            length = sum(diffs)
            for ii in range(dists.shape[1]):
                dists[:,ii] = dists[:,ii]*diffs[ii]/length
        else:
            dists = self.dists[:,self.layer > 0]
        bulk_dist = nanmean(dists, axis=1)
        bulk_dist = 100 * bulk_dist / bulk_dist.sum()
        return bulk_dist

    def bulk_mean(self, gs_min_max=None):
        """
        calculate bulk mean of all samples of tsunami sediments in trench

        gs_min_max is a sequence of length 2 specifying the minimum grain size
        and maximum grain size to include in the calculations (in phi)
        """
        if self.bins_phi_mid is None:
            return np.nan
        else:
            dist = self.bulk_dist()
            if gs_min_max is not None:
                f1 = gs_min_max[0] >= self.bins_phi_mid
                f2 = gs_min_max[1] <= self.bins_phi_mid
                filtr = f1 * f2
                dist = dist[filtr]
                bins = self.bins_phi_mid[filtr]
            else:
                bins = self.bins_phi_mid
            return np.sum(dist*bins) / dist.sum()

    def _get_depth_bin_edges(self, min_layer=-2):
        """
        internal method to deal with uneven depth spacing when plotting pcolor

        eg if min_depth = [0, 1, 2.5], max_depth = [1, 2, 3.5]
        returns [0, 1, 2.25, 3.5]

        min_layer designates the lower boundary of layers to use from the
        layer attribute field
        """
        min_depth = self.min_depth[self.layer > min_layer]
        max_depth = self.max_depth[self.layer > min_layer]
        ## all sample edges match
        if np.array_equal(min_depth[1:], max_depth[:-1]):
            return np.hstack((min_depth, max_depth[-1]))
        ## some sample edges do not match
        else:
            depths = np.zeros(self.min_depth.size+1)
            depths[0] = min_depth[0]
            depths[-1] = max_depth[-1]
            for ii, (n, x) in enumerate(zip(min_depth[1:],
                                            max_depth[:-1])):
                ii += 1
                if n == x:
                    depths[ii] = n
                else:
                    depths[ii] = n + (x-n)/2
            return depths

    def fig_dists_depth(self, figsize=(8,10), phi_min=-2, phi_max=4,
                         pcolor=True, tsunami_only=True, min_layer=None):
        """
        create a matplotlib figure plotting grain size distribution with depth

        phi_min is the minimum phi value (maximum grain size)
        phi_max is the maximum phi value (minimum grain size)
        """
        fig = plt.figure(figsize=figsize)
        ax = plt.subplot(111)
        plt.title('Grain-size distributions at %s' % self.id)
        ## set layer filter value
        if min_layer is None:
            if tsunami_only:
                min_layer = 0
            else:
                min_layer = -2
        ## filter dists so that only layer values > min_layer are plotted
        dists = self.dists[:,self.layer > min_layer]
        max_depth = self.max_depth[self.layer > min_layer]
        min_depth = self.min_depth[self.layer > min_layer]
        ## check that depth data exists
        if np.isnan(max_depth).all():
            plt.text(.5, .5, 'No depth values associated with grain-size data',
                     ha='center')
            return fig
        elif np.isnan(max_depth).any():
            pcolor = False
        ## create pcolor
        if pcolor:
            depths = self._get_depth_bin_edges(min_layer=min_layer)
            plt.pcolormesh(self.bins_phi_mid, depths, dists.T)
            color = 'w'
            cbar = plt.colorbar(orientation='vertical', fraction=.075, pad=.1,
                                aspect=30, shrink=.75)
            cbar.set_label(self.distribution_units)
        else:
            color = 'k'
        ## set phi bins
        if self.bins_phi is not None:
            bins = self.bins_phi
        elif self.bins_phi_mid is not None:
            bins = self.bins_phi_mid
        else:
            plt.text(.5, .5,
                     'Grain size bins must convert to phi for this figure',
                     ha='center')
            return fig
        ## plot a line for each distribution
        for ii, d in enumerate(max_depth):
            ## normalize to the max, and scale to plot within the depth range
            normed = dists[:,ii]*(min_depth[ii]-d)*.95/dists[:,ii].max()
            plt.plot(bins, d+normed, color, lw=2.25)
        ax.invert_yaxis()
        ax.set_xlim((phi_min, phi_max))
        ax.set_ylim(bottom=np.nanmax(max_depth))
        plt.xlabel('Size (\u03D5)')
        plt.ylabel('Depth (%s)' % self.depth_units)
        return fig

    def fig_dists_stacked(self, figsize=(16,12), phi_min=-2, phi_max=4,
                            tsunami_only=True, min_layer=None):
        """
        plot grain size distributions on one axis
        """
        fig = plt.figure(figsize=figsize)
        ax = plt.subplot(111)
        plt.title('Grain size distributions at %s' % self.id)
        ## set layer filter value
        if min_layer is None:
            if tsunami_only:
                min_layer = 0
            else:
                min_layer = -2
        ## filter dists so that only layer values > min_layer are plotted
        dists = self.dists[:, self.layer > min_layer]
        n_dists = dists.shape[1]
        labels = [self.sample_id[ii] for ii, L in enumerate(self.layer) if L > min_layer]
        ## set up custom cmap
        cmap = cm.get_cmap('spectral')
        c = [cmap(1.*((ii+1)/(n_dists+1))) for ii in range(n_dists)]
        ## set phi bins
        if self.bins_phi is not None:
            bins = self.bins_phi
        elif self.bins_phi_mid is not None:
            bins = self.bins_phi_mid
        else:
            plt.text(.5, .5,
                     'Grain size bins must convert to phi for this figure',
                     ha='center')
            return fig
        ## plot each distribution
        for ii, d in enumerate(dists.T):
            plt.plot(bins, d, c=c[ii], label=labels[ii], lw=1.5)
        plt.legend(loc=0)
        ax.set_xlim((phi_min, phi_max))
        plt.ylabel(self.distribution_units)
        plt.xlabel('Size (\u03D5)')
        return fig

class SedlabGSFile(GSFile):
    """
    Load grainsize data from an excel spreadsheet in the format used by the
    USGS PCMSC Sed Lab (current as of Feb. 26, 2015).
    """

    def read_GSData(self, filename, sheetname='Grain Size'):
        data = pd.read_excel(filename, sheetname, skiprows=2)

        FAnum = pd.read_excel(filename, sheetname, parse_cols=0).columns.values[0]

        # get phi bins
        end_phi_idx = np.where(data.columns == [s for s in data.columns if '%'
                                                in str(s)][0])[0][0]
        phi = np.asarray(data.columns[3:end_phi_idx], dtype = np.float64)

        # get sample ids and depths
        for idx, i in enumerate(list(data[data.columns[0]])):
            if type(i) == float:
                end = idx
                break
        ids = [str(s).split(' ') for s in list(data[data.columns[0]][:end])]
        SampleID = list(data[data.columns[1]])[:end]
        TrenchName = []
        MinDepth = []
        MaxDepth = []
        for i in ids:
            if '-' in i:
                for s in i:
                    if set('-') & set(s):
                        split = i.index(s)
                MinDepth.append(float(i[split-1]))
                MaxDepth.append(float(i[split+1]))
                TrenchName.append(" ".join(i[0:split-1]))
            else:
                MinDepth.append('nan')
                MaxDepth.append('nan')
                TrenchName.append(" ".join(i[0:]))

        # get layer numbers
        layernum = []
        for idx, n in enumerate(TrenchName):
            if idx == 0:
                layernum.append(1)
                continue
            if n == TrenchName[idx-1]:
                layernum.append(layernum[idx-1]+1)
            else:
                layernum.append(1)

        # get grain size data
        gsdata = np.array(data.iloc[:end,3:phi.size+3], dtype = np.float64)


        # set metadata attributes
        self.bin_units = 'phi'
        self.depth_units = 'cm'
        self.id = FAnum
        self.distribution_units = 'percent'
        self.whosgs = 'USGS PCMSC Sed Lab'
        self.gsfileoriginal = filename

        # set grainsize data attributes
        self.layer = np.asarray(layernum, dtype = np.int)
        self.sample_id = np.asarray(SampleID)
        self.min_depth = np.asarray(MinDepth, dtype = np.float64)
        self.max_depth = np.asarray(MaxDepth, dtype = np.float64)
        self.bins = phi
        self.bins_phi = self._convert_bins_to_phi()
        self.bins_phi_mid = self._convert_bins_to_phi_mid()
        self.dists = gsdata.T
        self.mid_depth = (self.min_depth+self.max_depth) / 2
