#!/usr/bin/env python
"""
Visual pseudosection explorer for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

from .utils import *

import argparse
import time
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.colorbar import ColorbarBase
from mpl_toolkits.axes_grid1 import make_axes_locatable

from shapely.geometry import MultiPoint
from descartes import PolygonPatch
from scipy.interpolate import Rbf
from scipy.interpolate import interp1d
from tqdm import tqdm, trange


class PTPS:
    def __init__(self, psb):
        self.psb = psb
        prj = TCAPI(psb.data.get('workdir'))
        if prj.OK:
            self.prj = prj
        else:
            print('Error during initialization of {} directory'.format(psb.data.get('workdir')), prj.status)
        if self.gridfile.is_file():
            with gzip.open(str(self.gridfile), 'rb') as stream:
                data = pickle.load(stream)
            self.shapes = data['shapes']
            self.edges = data['edges']
            self.variance = data['variance']
            self.tspace = data['tspace']
            self.pspace = data['pspace']
            self.tg = data['tg']
            self.pg = data['pg']
            self.gridcalcs = data['gridcalcs']
            self.masks = data['masks']
            self.status = data['status']
            self.delta = data['delta']
            self.uuid = data.get('uuid', '')
            self.ready = True
            self.gridded = True
            # update variable lookup table
            self.collect_all_data_keys()
            if self.uuid != self.psb.uuid:
                self.refresh_geometry()
                print('Project file changed from last gridding. Consider regridding.')
        else:
            self.gridded = False
            # refresh shapes
            self.refresh_geometry()

    @classmethod
    def from_file(cls, projfile):
        psb = PSB.from_file(projfile)
        return cls(psb)

    def __iter__(self):
        if self.ready:
            return iter(self.shapes)
        else:
            return iter([])

    def __repr__(self):
        if self.gridded:
            if self.uuid == self.psb.uuid:
                gstatus = 'OK'
            else:
                gstatus = 'Need regridding'
            gtxt = '\n'.join(['Grid file: {} [{}]'.format(self.gridfile.name, gstatus),
                              'T steps: {}'.format(len(self.tspace)),
                              'p steps: {}'.format(len(self.pspace))])
        else:
            gtxt = 'Not yet gridded'
        return '\n'.join([repr(self.psb),
                          '============',
                          'Gridded data',
                          '============',
                          gtxt,
                          repr(self.prj)])

    @property
    def phases(self):
        return {phase for key in self for phase in key}

    @property
    def keys(self):
        return list(self.shapes.keys())

    @property
    def tstep(self):
        return self.tspace[1] - self.tspace[0]

    @property
    def pstep(self):
        return self.pspace[1] - self.pspace[0]

    @property
    def ratio(self):
        return (self.psb.trange[1] - self.psb.trange[0]) / (self.psb.prange[1] - self.psb.prange[0])

    @property
    def gridfile(self):
        return self.prj.workdir.joinpath(self.psb.name).with_suffix('.psi')

    def unidata(self, fid):
        return self.psb.unidata(fid)

    def invdata(self, fid):
        return self.psb.invdata(fid)

    def save(self):
        if self.ready and self.gridded:
            # put to dict
            self.uuid = self.psb.uuid
            data = {'shapes': self.shapes,
                    'edges': self.edges,
                    'variance': self.variance,
                    'tspace': self.tspace,
                    'pspace': self.pspace,
                    'tg': self.tg,
                    'pg': self.pg,
                    'gridcalcs': self.gridcalcs,
                    'masks': self.masks,
                    'status': self.status,
                    'delta': self.delta,
                    'uuid': self.uuid}
            # do save
            with gzip.open(str(self.gridfile), 'wb') as stream:
                pickle.dump(data, stream)

    def refresh_geometry(self):
        # Create shapes
        self.shapes, self.edges, self.bad_shapes = self.psb.create_shapes()
        # calculate variance
        self.variance = {}
        for key in self.shapes:
            ans = '{}\nkill\n\n'.format(' '.join(key))
            tcout = self.prj.runtc(ans)
            for ln in tcout.splitlines():
                if 'variance of required equilibrium' in ln:
                    break
            self.variance[key] = int(ln[ln.index('(') + 1:ln.index('?')])
        self.ready = True

    def gendrawpd(self, export_areas=True):
        #self.refresh_geometry()
        with self.prj.drawpdfile.open('w', encoding=self.prj.TCenc) as output:
            output.write('% Generated by PyPSbuilder (c) Ondrej Lexa 2019\n')
            output.write('2    % no. of variables in each line of data, in this case P, T\n')
            exc = frozenset.intersection(*self.keys)
            nc = frozenset.union(*self.keys)
            # ex.insert(0, '')
            output.write('{}'.format(len(nc) - len(exc)) + '\n')
            output.write('2 1  %% which columns to be x,y in phase diagram\n')
            output.write('\n')
            output.write('% Points\n')
            for i in self.psb.invlist:
                output.write('% ------------------------------\n')
                output.write('i%s   %s\n' % (i[0], i[1]))
                output.write('\n')
                output.write('%s %s\n' % (i[2]['p'][0], i[2]['T'][0]))
                output.write('\n')
            output.write('% Lines\n')
            for u in self.psb.unilist:
                output.write('% ------------------------------\n')
                output.write('u%s   %s\n' % (u[0], u[1]))
                output.write('\n')
                b1 = 'i%s' % u[2]
                if b1 == 'i0':
                    b1 = 'begin'
                b2 = 'i%s' % u[3]
                if b2 == 'i0':
                    b2 = 'end'
                if u[4]['manual']:
                    output.write(b1 + ' ' + b2 + ' connect\n')
                    output.write('\n')
                else:
                    output.write(b1 + ' ' + b2 + '\n')
                    output.write('\n')
                    for p, t in zip(u[4]['p'], u[4]['T']):
                        output.write('%s %s\n' % (p, t))
                    output.write('\n')
            output.write('*\n')
            output.write('% ----------------------------------------------\n\n')
            if export_areas:
                # phases in areas for TC-Investigator
                with self.prj.workdir.joinpath('assemblages.txt').open('w') as tcinv:
                    vertices, edges, phases, tedges, tphases = self.psb.construct_areas()
                    # write output
                    output.write('% Areas\n')
                    output.write('% ------------------------------\n')
                    maxpf = max([len(p) for p in phases]) + 1
                    for ed, ph, ve in zip(edges, phases, vertices):
                        v = np.array(ve)
                        if not (np.all(v[:, 0] < self.psb.trange[0]) or
                                np.all(v[:, 0] > self.psb.trange[1]) or
                                np.all(v[:, 1] < self.psb.prange[0]) or
                                np.all(v[:, 1] > self.psb.prange[1])):
                            d = ('{:.2f} '.format(len(ph) / maxpf) +
                                 ' '.join(['u{}'.format(e) for e in ed]) +
                                 ' % ' + ' '.join(ph) + '\n')
                            output.write(d)
                            tcinv.write(' '.join(ph.union(exc)) + '\n')
                    for ed, ph in zip(tedges, tphases):
                        d = ('{:.2f} '.format(len(ph) / maxpf) +
                             ' '.join(['u{}'.format(e) for e in ed]) +
                             ' %- ' + ' '.join(ph) + '\n')
                        output.write(d)
                        tcinv.write(' '.join(ph.union(exc)) + '\n')
            output.write('\n')
            output.write('*\n')
            output.write('\n')
            output.write('window {} {} '.format(*self.psb.trange) +
                         '{} {}\n\n'.format(*self.psb.prange))
            output.write('darkcolour  56 16 101\n\n')
            dt = self.psb.trange[1] - self.psb.trange[0]
            dp = self.psb.prange[1] - self.psb.prange[0]
            ts = np.power(10, np.int(np.log10(dt)))
            ps = np.power(10, np.int(np.log10(dp)))
            tg = np.arange(0, self.psb.trange[1] + ts, ts)
            tg = tg[tg >= self.psb.trange[0]]
            pg = np.arange(0, self.psb.prange[1] + ps, ps)
            pg = pg[pg >= self.psb.prange[0]]
            output.write('bigticks ' +
                         '{} {} '.format(tg[1] - tg[0], tg[0]) +
                         '{} {}\n\n'.format(pg[1] - pg[0], pg[0]))
            output.write('smallticks {} '.format((tg[1] - tg[0]) / 10) +
                         '{}\n\n'.format((pg[1] - pg[0]) / 10))
            output.write('numbering yes\n\n')
            if export_areas:
                output.write('doareas yes\n\n')
            output.write('*\n')
            print('Drawpd file generated successfully.')

        if self.prj.rundr():
            print('Drawpd sucessfully executed.')
        else:
            print('Drawpd error!', str(err))

    def calculate_composition(self, numT=51, numP=51):
        self.tspace = np.linspace(self.psb.trange[0], self.psb.trange[1], numT)
        self.pspace = np.linspace(self.psb.prange[0], self.psb.prange[1], numP)
        self.tg, self.pg = np.meshgrid(self.tspace, self.pspace)
        self.gridcalcs = np.empty(self.tg.shape, np.dtype(object))
        self.status = np.empty(self.tg.shape)
        self.status[:] = np.nan
        self.delta = np.empty(self.tg.shape)
        self.delta[:] = np.nan
        # check shapes created
        #if not self.ready:
        #    self.refresh_geometry()
        # do grid calculation
        for (r, c) in tqdm(np.ndindex(self.tg.shape), desc='Gridding', total=np.prod(self.tg.shape)):
            t, p = self.tg[r, c], self.pg[r, c]
            k = self.identify(t, p)
            if k is not None:
                self.status[r, c] = 0
                start_time = time.time()
                tcout, ans = self.prj.tc_calc_assemblage(k.difference(self.prj.excess), p, t)
                delta = time.time() - start_time
                status, variance, pts, res, output = self.prj.parse_logfile()
                if len(res) == 1:
                    self.gridcalcs[r, c] = res[0]
                    self.status[r, c] = 1
                    self.delta[r, c] = delta
                # search already done inv neighs
                if self.status[r, c] == 0:
                    edges = self.edges[k]
                    for inv in {self.unidata(ed)['begin'] for ed in edges}.union({self.unidata(ed)['end'] for ed in edges}).difference({0}):
                        if not self.invdata(inv)['manual']:
                            self.prj.update_scriptfile(guesses=self.invdata(inv)['results'][0]['ptguess'])
                            start_time = time.time()
                            tcout = self.prj.runtc(ans)
                            delta = time.time() - start_time
                            status, variance, pts, res, output = self.prj.parse_logfile()
                            if len(res) == 1:
                                self.gridcalcs[r, c] = res[0]
                                self.status[r, c] = 1
                                self.delta[r, c] = delta
                                break
                    if self.status[r, c] == 0:
                        self.gridcalcs[r, c] = None
            else:
                self.gridcalcs[r, c] = None
        print('Grid search done. {} empty grid points left.'.format(len(np.flatnonzero(self.status == 0))))
        self.gridded = True
        self.fix_solutions()
        self.create_masks()
        # update variable lookup table
        self.collect_all_data_keys()
        # save
        self.save()

    def create_masks(self):
        if self.ready and self.gridded:
            # Create data masks
            points = MultiPoint(list(zip(self.tg.flatten(), self.pg.flatten())))
            self.masks = OrderedDict()
            for key in tqdm(self, desc='Masking', total=len(self.shapes)):
                self.masks[key] = np.array(list(map(self.shapes[key].contains, points))).reshape(self.tg.shape)

    def fix_solutions(self):
        if self.gridded:
            ri, ci = np.nonzero(self.status == 0)
            fixed, ftot = 0, len(ri)
            tq = trange(ftot, desc='Fix ({}/{})'.format(fixed, ftot))
            for ind in tq:
                r, c = ri[ind], ci[ind]
                t, p = self.tg[r, c], self.pg[r, c]
                k = self.identify(t, p)
                if k is not None:
                    # search already done grid neighs
                    for rn, cn in self.neighs(r, c):
                        if self.status[rn, cn] == 1:
                            self.prj.update_scriptfile(guesses=self.gridcalcs[rn, cn]['ptguess'])
                            start_time = time.time()
                            tcout, ans = self.prj.tc_calc_assemblage(k.difference(self.prj.excess), p, t)
                            delta = time.time() - start_time
                            status, variance, pts, res, output = self.prj.parse_logfile()
                            if len(res) == 1:
                                self.gridcalcs[r, c] = res[0]
                                self.status[r, c] = 1
                                self.delta[r, c] = delta
                                fixed += 1
                                tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                                break
                if self.status[r, c] == 0:
                    tqdm.write('No solution find for {}, {}'.format(t, p))
            print('Fix done. {} empty grid points left.'.format(len(np.flatnonzero(self.status == 0))))

    def neighs(self, r, c):
        m = np.array([[(r - 1, c - 1), (r - 1, c), (r - 1, c + 1)],
                      [(r, c - 1), (None, None), (r, c + 1)],
                      [(r + 1, c - 1), (r + 1, c), (r + 1, c + 1)]])
        if r < 1:
            m = m[1:, :]
        if r > len(self.pspace) - 2:
            m = m[:-1, :]
        if c < 1:
            m = m[:, 1:]
        if c > len(self.tspace) - 2:
            m = m[:, :-1]
        return zip([i for i in m[:, :, 0].flat if i is not None],
                   [i for i in m[:, :, 1].flat if i is not None])

    def calc_along_path(self, tpath, ppath, N=100, kind = 'quadratic'):
        if self.gridded:
            tpath, ppath = np.asarray(tpath), np.asarray(ppath)
            assert tpath.shape == ppath.shape, 'Shape of temeratures and pressures should be same.'
            assert tpath.ndim == 1, 'Temeratures and pressures should be 1D array like data.'
            gpath = np.arange(tpath.shape[0], dtype=float)
            gpath /= gpath[-1]
            splt = interp1d(gpath, tpath, kind=kind)
            splp = interp1d(gpath, ppath, kind=kind)
            err = 0
            dt = dict(pts=[], res=[])
            for step in tqdm(np.linspace(0, 1, N), desc='Calculating'):
                t, p = splt(step), splp(step)
                key = self.identify(t, p)
                mask = self.masks[key]
                dst = (t - self.tg)**2 + (self.ratio*(p - self.pg))**2
                dst[~mask] = np.nan
                r, c = np.unravel_index(np.nanargmin(dst), self.tg.shape)
                calc = None
                if self.status[r, c] == 1:
                    calc = self.gridcalcs[r, c]
                else:
                    for rn, cn in self.neighs(r, c):
                        if self.status[rn, cn] == 1:
                            calc = self.gridcalcs[rn, cn]
                            break
                if calc is not None:
                    self.prj.update_scriptfile(guesses=calc['ptguess'])
                    tcout, ans = self.prj.tc_calc_assemblage(key.difference(self.prj.excess), p, t)
                    status, variance, pts, res, output = self.prj.parse_logfile()
                    if len(res) == 1:
                        dt['pts'].append((t, p))
                        dt['res'].append(res[0])
                else:
                    err += 1
            if err > 0:
                print('Solution not found on {} points'.format(err))
            return dt

    def collect_all_data_keys(self):
        data = dict()
        if self.ready and self.gridded:
            for key in self:
                res = self.gridcalcs[self.masks[key]]
                if len(res) > 0:
                    for k in res[0]['data'].keys():
                        data[k] = list(res[0]['data'][k].keys())
        self.all_data_keys = data

    def collect_inv_data(self, key, phase, expr):
        dt = dict(pts=[], data=[])
        if self.ready:
            edges = self.edges[key]
            for i in {self.unidata(ed)['begin'] for ed in edges}.union({self.unidata(ed)['end'] for ed in edges}).difference({0}):
                if not self.invdata(i)['manual']:
                    T = self.invdata(i)['T'][0]
                    p = self.invdata(i)['p'][0]
                    res = self.invdata(i)['results'][0]
                    v = eval_expr(expr, res['data'][phase])
                    dt['pts'].append((T, p))
                    dt['data'].append(v)
        return dt

    def collect_edges_data(self, key, phase, expr):
        dt = dict(pts=[], data=[])
        if self.ready:
            for e in self.edges[key]:
                if not self.unidata(e)['manual']:
                    bix, eix = self.unidata(e)['begix'], self.unidata(e)['endix']
                    edt = zip(self.unidata(e)['T'][bix:eix + 1],
                              self.unidata(e)['p'][bix:eix + 1],
                              self.unidata(e)['results'][bix:eix + 1])
                    for T, p, res in edt:
                        v = eval_expr(expr, res['data'][phase])
                        dt['pts'].append((T, p))
                        dt['data'].append(v)
        return dt

    def collect_grid_data(self, key, phase, expr):
        dt = dict(pts=[], data=[])
        if self.ready and self.gridded:
            gdt = zip(self.tg[self.masks[key]],
                      self.pg[self.masks[key]],
                      self.gridcalcs[self.masks[key]],
                      self.status[self.masks[key]])
            for T, p, res, ok in gdt:
                if ok == 1:
                    v = eval_expr(expr, res['data'][phase])
                    dt['pts'].append((T, p))
                    dt['data'].append(v)
        return dt

    def collect_data(self, key, phase, expr, which=7):
        dt = dict(pts=[], data=[])
        if which & (1 << 0):
            d = self.collect_inv_data(key, phase, expr)
            dt['pts'].extend(d['pts'])
            dt['data'].extend(d['data'])
        if which & (1 << 1):
            d = self.collect_edges_data(key, phase, expr)
            dt['pts'].extend(d['pts'])
            dt['data'].extend(d['data'])
        if which & (1 << 2):
            d = self.collect_grid_data(key, phase, expr)
            dt['pts'].extend(d['pts'])
            dt['data'].extend(d['data'])
        return dt

    def merge_data(self, phase, expr, which=7):
        mn, mx = sys.float_info.max, -sys.float_info.max
        recs = OrderedDict()
        for key in self:
            res = self.gridcalcs[self.masks[key]]
            if len(res) > 0:
                if phase in res[0]['data']:
                    d = self.collect_data(key, phase, expr, which=which)
                    z = d['data']
                    if z:
                        recs[key] = d
                        mn = min(mn, min(z))
                        mx = max(mx, max(z))
        return recs, mn, mx

    def show(self, **kwargs):
        out = kwargs.get('out', None)
        cmap = kwargs.get('cmap', 'Purples')
        alpha = kwargs.get('alpha', 0.6)
        label = kwargs.get('label', False)
        bulk = kwargs.get('bulk', False)

        if isinstance(out, str):
            out = [out]
        # check shapes created
        #if not self.ready:
        #    self.refresh_geometry()
        if self.shapes:
            vari = [self.variance[k] for k in self]
            poc = max(vari) - min(vari) + 1
            pscolors = plt.get_cmap(cmap)(np.linspace(0, 1, poc))
            # Set alpha
            pscolors[:, -1] = alpha
            pscmap = ListedColormap(pscolors)
            norm = BoundaryNorm(np.arange(min(vari) - 0.5, max(vari) + 1.5), poc, clip=True)
            fig, ax = plt.subplots()
            for k in self:
                ax.add_patch(PolygonPatch(self.shapes[k], fc=pscmap(norm(self.variance[k])), ec='none'))
            ax.autoscale_view()
            self.add_overlay(ax, label=label)
            if out:
                for o in out:
                    lst = [self.psb.get_trimmed_uni(row[0]) for row in self.psb.unilist if o in row[4]['out']]
                    if lst:
                        ax.plot(np.hstack([(*seg[0], np.nan) for seg in lst]),
                                np.hstack([(*seg[1], np.nan) for seg in lst]),
                                lw=2, label=o)
                # Shrink current axis's width
                box = ax.get_position()
                ax.set_position([box.x0 + box.width * 0.07, box.y0, box.width * 0.95, box.height])
                # Put a legend below current axis
                ax.legend(loc='upper right', bbox_to_anchor=(-0.08, 1), title='Out', borderaxespad=0, frameon=False)
            divider = make_axes_locatable(ax)
            cax = divider.append_axes('right', size='4%', pad=0.05)
            cb = ColorbarBase(ax=cax, cmap=pscmap, norm=norm, orientation='vertical', ticks=np.arange(min(vari), max(vari) + 1))
            cb.set_label('Variance')
            ax.axis(self.psb.trange + self.psb.prange)
            if bulk:
                if label:
                    ax.set_xlabel(self.psb.name + (len(self.prj.excess) * ' +{}').format(*self.prj.excess))
                else:
                    ax.set_xlabel(self.psb.name)
                # bulk composition
                ox, vals = self.psb.get_bulk_composition()
                table = r'''\begin{tabular}{ ''' + ' | '.join(len(ox)*['c']) + '}' + ' & '.join(ox) + r''' \\\hline ''' + ' & '.join(vals) + r'''\end{tabular}'''
                plt.figtext(0.08, 0.94, table, size=10, va='top', usetex=True)
            else:
                if label:
                    ax.set_title(self.psb.name + (len(self.prj.excess) * ' +{}').format(*self.prj.excess))
                else:
                    ax.set_title(self.psb.name)
            # connect button press
            cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
            plt.show()
            # return ax
        else:
            print('There is no single area defined in your pseudosection. Check topology.')

    def add_overlay(self, ax, fc='none', ec='k', label=False):
        for k in self:
            ax.add_patch(PolygonPatch(self.shapes[k], ec=ec, fc=fc, lw=0.5))
            if label:
                # multiline for long labels
                tl = sorted(list(k.difference(self.prj.excess)))
                wp = len(tl) // 4 + int(len(tl) % 4 > 1)
                txt = '\n'.join([' '.join(s) for s in [tl[i * len(tl) // wp: (i + 1) * len(tl) // wp] for i in range(wp)]])
                xy = self.shapes[k].representative_point().coords[0]
                ax.annotate(s=txt, xy=xy, weight='bold', fontsize=6, ha='center', va='center')

    def show_data(self, key, phase, expr, which=7):
        dt = self.collect_data(key, phase, expr, which=which)
        x, y = np.array(dt['pts']).T
        fig, ax = plt.subplots()
        pts = ax.scatter(x, y, c=dt['data'])
        ax.set_title('{} - {}({})'.format(' '.join(key), phase, expr))
        plt.colorbar(pts)
        plt.show()

    def show_status(self, label=False):
        fig, ax = plt.subplots()
        extent = (self.psb.trange[0] - self.tstep / 2, self.psb.trange[1] + self.tstep / 2,
                  self.psb.prange[0] - self.pstep / 2, self.psb.prange[1] + self.pstep / 2)
        cmap = ListedColormap(['orangered', 'limegreen'])
        ax.imshow(self.status, extent=extent, aspect='auto', origin='lower', cmap=cmap)
        self.add_overlay(ax, label=label)
        plt.axis(self.psb.trange + self.psb.prange)
        plt.title('Gridding status - {}'.format(self.psb.name))
        plt.show()

    def show_delta(self, label=False):
        fig, ax = plt.subplots()
        extent = (self.psb.trange[0] - self.tstep / 2, self.psb.trange[1] + self.tstep / 2,
                  self.psb.prange[0] - self.pstep / 2, self.psb.prange[1] + self.pstep / 2)
        im = ax.imshow(self.delta, extent=extent, aspect='auto', origin='lower')
        self.add_overlay(ax, label=label)
        cb = plt.colorbar(im)
        cb.set_label('sec/point')
        plt.title('THERMOCALC execution time - {}'.format(self.psb.name))
        plt.axis(self.psb.trange + self.psb.prange)
        plt.show()

    def show_path_data(self, dt, phase, expr, label=False, pathwidth=4, allpath=True):
        from matplotlib.collections import LineCollection
        from matplotlib.colors import ListedColormap, BoundaryNorm

        t, p, ex = self.get_path_data(dt, phase, expr)

        fig, ax = plt.subplots()
        if allpath:
            ax.plot(t, p, '--', color='grey', lw=1)
        # Create a continuous norm to map from data points to colors
        norm = plt.Normalize(np.nanmin(ex), np.nanmax(ex))

        for s in np.ma.clump_unmasked(np.ma.masked_invalid(ex)):
            ts, ps, exs = t[s], p[s], ex[s]
            points = np.array([ts, ps]).T.reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            lc = LineCollection(segments, cmap='viridis', norm=norm)
            # Set the values used for colormapping
            lc.set_array(exs)
            lc.set_linewidth(pathwidth)
            line = ax.add_collection(lc)
            self.add_overlay(ax, label=label)
        cb = plt.colorbar(line, ax=ax)
        cb.set_label('{}[{}]'.format(phase, expr))
        plt.axis(self.psb.trange + self.psb.prange)
        plt.title('PT path - {}'.format(self.psb.name))
        plt.show()

    def show_path_modes(self, dt, exclude=[], cmap='tab20'):
        t, p = np.array(dt['pts']).T
        steps = len(t)
        nd = np.linspace(0, 1, steps)
        splt = interp1d(nd, t, kind='quadratic')
        splp = interp1d(nd, p, kind='quadratic')
        pset = set()
        for res in dt['res']:
            pset.update(res['data'].keys())

        pset = pset.difference(exclude)
        phases = sorted(list(pset))
        modes = []
        for phase in phases:
            modes.append(np.array([100*res['data'][phase]['mode'] if phase in res['data'] else 0 for res in dt['res']]))

        cm = plt.get_cmap(cmap)
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.set_prop_cycle(color=[cm(i/len(phases)) for i in range(len(phases))])
        bottom = np.zeros_like(modes[0])
        bars = []
        for n, mode in enumerate(modes):
            h = ax.bar(nd, mode, bottom=bottom, width=nd[1]-nd[0])
            bars.append(h[0])
            bottom += mode

        ax.format_coord = lambda x, y: 'T={:.2f} p={:.2f}'.format(splt(x), splp(x))
        ax.set_xlim(0, 1)
        ax.set_xlabel('Normalized distance along path')
        ax.set_ylabel('Mode [%]')
        plt.legend(bars, phases, fancybox=True, loc='center right', bbox_to_anchor=(1.1,0.5))
        plt.show()

    def identify(self, T, p):
        for key in self:
            if Point(T, p).intersects(self.shapes[key]):
                return key

    def onclick(self, event):
        if event.button == 1:
            if event.inaxes:
                key = self.identify(event.xdata, event.ydata)
                if key:
                    print(' '.join(sorted(list(key))))

    def isopleths(self, phase, expr, **kwargs):
        # parse kwargs
        which = kwargs.get('which', 7)
        smooth = kwargs.get('smooth', 0)
        filled = kwargs.get('filled', True)
        out = kwargs.get('out', True)
        bulk = kwargs.get('bulk', False)
        nosplit = kwargs.get('nosplit', True)
        step = kwargs.get('step', None)
        N = kwargs.get('N', 10)
        gradient = kwargs.get('gradient', False)
        dt = kwargs.get('dt', True)
        only = kwargs.get('only', None)
        refine = kwargs.get('refine', 1)
        colors = kwargs.get('colors', None)
        cmap = kwargs.get('cmap', 'viridis')
        clabel = kwargs.get('clabel', [])

        if not self.gridded:
            print('Collecting only from uni lines and inv points. Not yet gridded...')
        if only is not None:
            recs = OrderedDict()
            d = self.collect_data(only, phase, expr, which=which)
            z = d['data']
            if z:
                recs[only] = d
                mn = min(z)
                mx = max(z)
        else:
            recs, mn, mx = self.merge_data(phase, expr, which=which)
        if step:
            cntv = np.arange(0, mx + step, step)
            cntv = cntv[cntv >= mn - step]
        else:
            dm = (mx - mn) / 25
            #cntv = np.linspace(max(0, mn - dm), mx + dm, N)
            cntv = np.linspace(mn - dm, mx + dm, N)
        # Thin-plate contouring of areas
        fig, ax = plt.subplots()
        for key in recs:
            tmin, pmin, tmax, pmax = self.shapes[key].bounds
            # ttspace = self.tspace[np.logical_and(self.tspace >= tmin - self.tstep, self.tspace <= tmax + self.tstep)]
            # ppspace = self.pspace[np.logical_and(self.pspace >= pmin - self.pstep, self.pspace <= pmax + self.pstep)]
            ttspace = np.arange(tmin - self.tstep, tmax + self.tstep, self.tstep / refine)
            ppspace = np.arange(pmin - self.pstep, pmax + self.pstep, self.pstep / refine)
            tg, pg = np.meshgrid(ttspace, ppspace)
            x, y = np.array(recs[key]['pts']).T
            try:
                # Use scaling
                rbf = Rbf(x, self.ratio * y, recs[key]['data'], function='thin_plate', smooth=smooth)
                zg = rbf(tg, self.ratio * pg)
                # experimental
                if gradient:
                    if dt:
                        zg = np.gradient(zg, self.tstep, self.pstep)[0]
                    else:
                        zg = -np.gradient(zg, self.tstep, self.pstep)[1]
                    if N:
                        cntv = N
                    else:
                        cntv = 10
                # ------------
                if filled:
                    cont = ax.contourf(tg, pg, zg, cntv, colors=colors, cmap=cmap)
                else:
                    cont = ax.contour(tg, pg, zg, cntv, colors=colors, cmap=cmap)
                patch = PolygonPatch(self.shapes[key], fc='none', ec='none')
                ax.add_patch(patch)
                for col in cont.collections:
                    col.set_clip_path(patch)
                # label if needed
                if not filled and key == set(clabel):
                    positions = []
                    for col in cont.collections:
                        for seg in col.get_segments():
                            inside = np.fromiter(map(self.shapes[key].contains, MultiPoint(seg)), dtype=bool)
                            if np.any(inside):
                                positions.append(seg[inside].mean(axis=0))
                    ax.clabel(cont, fontsize=9, manual=positions, fmt='%g', inline_spacing=3, inline=not nosplit)

            except Exception as e:
                print('{} for {}'.format(e.__class__.__name__, key))
        if only is None:
            self.add_overlay(ax)
            # zero mode line
            if out:
                lst = [self.psb.get_trimmed_uni(row[0]) for row in self.psb.unilist if phase in row[4]['out']]
                if lst:
                    ax.plot(np.hstack([(*seg[0], np.nan) for seg in lst]),
                            np.hstack([(*seg[1], np.nan) for seg in lst]),
                            lw=2)
        try:
            plt.colorbar(cont)
        except:
            print('There is trouble to draw colorbar. Sorry.')
        if bulk:
            if only is None:
                ax.axis(self.psb.trange + self.psb.prange)
                ax.set_xlabel('{}({})'.format(phase, expr))
            else:
                ax.set_xlabel('{} - {}({})'.format(' '.join(only), phase, expr))
            # bulk composition
            ox, vals = self.psb.get_bulk_composition()
            table = r'''\begin{tabular}{ ''' + ' | '.join(len(ox)*['c']) + '}' + ' & '.join(ox) + r''' \\\hline ''' + ' & '.join(vals) + r'''\end{tabular}'''
            plt.figtext(0.08, 0.94, table, size=10, va='top', usetex=True)
        else:
            if only is None:
                ax.axis(self.psb.trange + self.psb.prange)
                ax.set_title('{}({})'.format(phase, expr))
            else:
                ax.set_title('{} - {}({})'.format(' '.join(only), phase, expr))
        # connect button press
        cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
        plt.show()

    def get_gridded(self, phase, expr, which=7, smooth=0):
        if not self.gridded:
            print('Not yet gridded.')
        recs, mn, mx = self.merge_data(phase, expr, which=which)
        gd = np.empty(self.tg.shape)
        gd[:] = np.nan
        for key in recs:
            tmin, pmin, tmax, pmax = self.shapes[key].bounds
            ttind = np.logical_and(self.tspace >= tmin - self.tstep, self.tspace <= tmax + self.tstep)
            ppind = np.logical_and(self.pspace >= pmin - self.pstep, self.pspace <= pmax + self.pstep)
            slc = np.ix_(ppind, ttind)
            tg, pg = self.tg[slc], self.pg[slc]
            x, y = np.array(recs[key]['pts']).T
            # Use scaling
            rbf = Rbf(x, self.ratio * y, recs[key]['data'], function='thin_plate', smooth=smooth)
            zg = rbf(tg, self.ratio * pg)
            gd[self.masks[key]] = zg[self.masks[key][slc]]
        return gd

    def get_path_data(self, dt, phase, expr):
        t, p = np.array(dt['pts']).T
        ex = np.array([eval_expr(expr, res['data'][phase]) if phase in res['data'] else np.nan for res in dt['res']])
        return t, p, ex

    # Need FIX
    def save_tab(self, tabfile=None, comps=None):
        if not tabfile:
            tabfile = self.psb.name + '.tab'
        if not comps:
            comps = self.all_data_keys
        data = []
        for comp in tqdm(comps, desc='Exporting'):
            data.append(self.get_gridded(comp).flatten())
        with Path(tabfile).open('wb') as f:
            head = ['psbuilder', self.psb.name + '.tab', '{:12d}'.format(2),
                    'T(°C)', '   {:16.16f}'.format(self.psb.trange[0])[:19],
                    '   {:16.16f}'.format(self.tstep)[:19], '{:12d}'.format(len(self.tspace)),
                    'p(kbar)', '   {:16.16f}'.format(self.psb.prange[0])[:19],
                    '   {:16.16f}'.format(self.pstep)[:19], '{:12d}'.format(len(self.pspace)),
                    '{:12d}'.format(len(data)), (len(data) * '{:15s}').format(*comps)]
            for ln in head:
                f.write(bytes(ln + '\n', 'utf-8'))
            np.savetxt(f, np.transpose(data), fmt='%15.6f', delimiter='')
        print('Saved.')


def ps_show():
    parser = argparse.ArgumentParser(description='Draw pseudosection from project file')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('-o', '--out', nargs='+',
                        help='highlight out lines for given phases')
    parser.add_argument('-l', '--label', action='store_true',
                        help='show area labels')
    parser.add_argument('-b', '--bulk', action='store_true',
                        help='show bulk composition on figure')
    parser.add_argument('--cmap', type=str,
                        default='Purples', help='name of the colormap')
    parser.add_argument('--alpha', type=float,
                        default=0.6, help='alpha of colormap')
    args = parser.parse_args()
    ps = PTPS.from_file(args.project)
    sys.exit(ps.show(out=args.out, label=args.label, bulk=args.bulk,
                     cmap=args.cmap, alpha=args.alpha))


def ps_grid():
    parser = argparse.ArgumentParser(description='Calculate compositions in grid')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('--numT', type=int, default=51,
                        help='number of T steps')
    parser.add_argument('--numP', type=int, default=51,
                        help='number of P steps')
    args = parser.parse_args()
    ps = PTPS.from_file(args.project)
    sys.exit(ps.calculate_composition(numT=args.numT, numP=args.numP))


def ps_iso():
    parser = argparse.ArgumentParser(description='Draw isopleth diagrams')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('phase', type=str,
                        help='phase used for contouring')
    parser.add_argument('expr', type=str,
                        help='expression evaluated to calculate values')
    parser.add_argument('-f', '--filled', action='store_true',
                        help='filled contours')
    parser.add_argument('-o', '--out', action='store_true',
                        help='highlight out line for given phase')
    parser.add_argument('--nosplit', action='store_true',
                        help='controls whether the underlying contour is removed or not')
    parser.add_argument('-b', '--bulk', action='store_true',
                        help='show bulk composition on figure')
    parser.add_argument('--step', type=float,
                        default=None, help='contour step')
    parser.add_argument('--ncont', type=int,
                        default=10, help='number of contours')
    parser.add_argument('--colors', type=str,
                        default=None, help='color for all levels')
    parser.add_argument('--cmap', type=str,
                        default=None, help='name of the colormap')
    parser.add_argument('--smooth', type=float,
                        default=0, help='smoothness of the approximation')
    parser.add_argument('--clabel', nargs='+',
                        default=[], help='label contours in field defined by set of phases')
    args = parser.parse_args()
    ps = PTPS.from_file(args.project)
    sys.exit(ps.isopleths(args.phase, args.expr, filled=args.filled,
                          smooth=args.smooth, step=args.step, bulk=args.bulk,
                          N=args.ncont, clabel=args.clabel, nosplit=args.nosplit,
                          colors=args.colors, cmap=args.cmap, out=args.out))


def ps_drawpd():
    parser = argparse.ArgumentParser(description='Generate drawpd file from project')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('-a', '--areas', action='store_true',
                        help='export also areas', default=True)
    args = parser.parse_args()
    ps = PTPS.from_file(args.project)
    sys.exit(ps.gendrawpd(export_areas=args.areas))


if __name__ == "__main__":
    ps_show()
