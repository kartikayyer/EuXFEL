#!/usr/bin/env python

import sys
import h5py
import numpy as np
import glob
import geom

class AGIPD_Combiner():
    '''
    Interface to get frames interactively
    Initially specify path to folder with raw data
    Then use get_frame(num) to get specific frame
    '''
    def __init__(self, folder_path, verbose=0, good_cells=[4,8,12,16,20,24,28], geom_fname=None,
                 calib_file='/gpfs/exfel/exp/SPB/201701/p002012/scratch/filipe/offset_and_threshold.h5'):
        self.verbose = verbose
        self.good_cells = np.array(good_cells)*2
        self.geom_fname = geom_fname
        if self.geom_fname is not None:
            self.x, self.y = geom.pixel_maps_from_geometry_file(geom_fname)
        self._make_flist(folder_path)
        self._get_nframes_list()
        self.frame = np.empty((16,512,128))
        self.calib = h5py.File(calib_file,'r')
        
    def _make_flist(self, folder_path):
        self.flist = np.array([np.sort(glob.glob('%s/RAW-*-AGIPD%.2d*.h5'%(folder_path, r))) for r in range(16)])
        try:
            assert len(self.flist.shape) == 2
        except AssertionError:
            print('Each module does not have the same number of files')
            print([len(f) for f in self.flist])
        if self.verbose > 0:
            print('%d files per module' % len(self.flist[0]))

    def _get_nframes_list(self):
        module_nframes = np.zeros((16,), dtype='i4')
        self.nframes_list = []
        for i in range(16):
            for fname in self.flist[i]:
                with h5py.File(fname, 'r') as f:
                    try:
                        dset_name = '/INSTRUMENT/SPB_DET_AGIPD1M-1/DET/%dCH0:xtdf/image/data'%i
                        module_nframes[i] += f[dset_name].shape[0] / 60 * len(self.good_cells)
                        if i == 0:
                            self.nframes_list.append(f[dset_name].shape[0])
                        dset_name = '/INSTRUMENT/SPB_DET_AGIPD1M-1/DET/%dCH0:xtdf/image/trainId'%i
                    except KeyError:
                        print(fname)
                        raise
        try:
            assert np.all(module_nframes == module_nframes[0])
        except AssertionError:
            print('Not all modules have the same frames')
        if self.verbose > -1:
            print('%d good frames in run' % module_nframes[0])
        self.nframes = module_nframes[0]
        self.nframes_list = np.cumsum(self.nframes_list)

    def _calibrate(self, data, gain, module, cell):        
        data = np.float32(data)
        high_gain = gain < self.calib['threshold'][module,0,cell,:,:]
        low_gain = gain > self.calib['threshold'][module,1,cell,:,:]
        medium_gain =  ~high_gain * ~low_gain
        data -= self.calib['offset'][module,0,cell,:,:] * high_gain
        data -= self.calib['offset'][module,1,cell,:,:] * medium_gain
        data -= self.calib['offset'][module,2,cell,:,:] * low_gain
        data[medium_gain] *= 45
        data[low_gain] *= 45 * 3.8
        data[data < -100] = 0
        data[data > 10000] = 10000
        return data


    def _threshold(self, gain, module, cell):        
        high_gain = gain < self.calib['threshold'][module,0,cell,:,:]
        low_gain = gain > self.calib['threshold'][module,1,cell,:,:]
        medium_gain =  ~high_gain * ~low_gain
        return low_gain*2+medium_gain*1
        
    def _get_frame(self, num, type='frame', calibrate=False, threshold=False):
        if num > self.nframes or num < 0:
            print('Out of range')
            return
        
        cell_ind = num % len(self.good_cells)
        train_ind = num // len(self.good_cells)
        
        if type == 'frame':
            ind = self.good_cells[cell_ind] + train_ind * 60
        elif type == 'gain':
            ind = self.good_cells[cell_ind] + train_ind * 60 + 1
        else:
            raise ValueError        
        
        file_num = np.where(ind < self.nframes_list)[0][0]
        if file_num == 0:
            frame_num = ind 
        else:
            frame_num = ind - self.nframes_list[file_num-1]
        for i in range(16):
            if len(self.flist[i]) == 0:
                self.frame[i] = np.zeros_like(self.frame[0])
                continue
            with h5py.File(self.flist[i][file_num], 'r') as f:
                dset_name = '/INSTRUMENT/SPB_DET_AGIPD1M-1/DET/%dCH0:xtdf/image/data'%i
                data = f[dset_name][frame_num,0]                
                if calibrate:
                    data = self._calibrate(data,
                                           f[dset_name][frame_num+1,0],
                                           i, cell_ind)
                if threshold:
                    data = self._threshold(data, i, cell_ind)
                self.frame[i] = data
        if self.geom_fname is None:
            return self.frame
        else:
            return geom.apply_geom_ij_yx((self.x, self.y), self.frame)

    def get_frame(self, num, calibrate=False):
        return self._get_frame(num,type='frame', calibrate=calibrate)

    def get_gain(self, num, threshold=False):
        return self._get_frame(num,type='gain', calibrate=False, threshold=threshold)


        
