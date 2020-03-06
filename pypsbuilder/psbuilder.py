#!/usr/bin/env python
"""
Visual pseudosection builder for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

from .utils import *
from .psexplorer import PTPS

from pkg_resources import resource_filename
from PyQt5 import QtCore, QtGui, QtWidgets

import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)
from matplotlib.widgets import Cursor
from matplotlib import cm
from matplotlib.colors import ListedColormap, BoundaryNorm, Normalize
from descartes import PolygonPatch
import uuid

try:
    import networkx as nx
    NX_OK = True
except ImportError as e:
    NX_OK = False

from .ui_psbuilder import Ui_PSBuilder
from .ui_addinv import Ui_AddInv
from .ui_adduni import Ui_AddUni
from .ui_uniguess import Ui_UniGuess


__version__ = '2.2.0'
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

unihigh_kw = dict(lw=3, alpha=1, marker='o', ms=4, color='red', zorder=10)
invhigh_kw = dict(alpha=1, ms=8, color='red', zorder=10)
outhigh_kw = dict(lw=3, alpha=1, marker=None, ms=4, color='red', zorder=10)


class PSBuilder(QtWidgets.QMainWindow, Ui_PSBuilder):
    """Main class
    """
    def __init__(self, parent=None):
        super(PSBuilder, self).__init__(parent)
        self.setupUi(self)
        res = QtWidgets.QDesktopWidget().screenGeometry()
        self.resize(min(1024, res.width() - 10), min(768, res.height() - 10))
        self.setWindowTitle('PSBuilder')
        window_icon = resource_filename('pypsbuilder', 'images/pypsbuilder.png')
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.__changed = False
        self.about_dialog = AboutDialog(__version__)
        self.unihigh = None
        self.invhigh = None
        self.outhigh = None
        self.cid = None

        # Create figure
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self.tabPlot)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.mplvl.addWidget(self.canvas)
        self.toolbar = NavigationToolbar(self.canvas, self.tabPlot,
                                         coordinates=True)
        # remove "Edit curves lines and axes parameters"
        actions = self.toolbar.findChildren(QtWidgets.QAction)
        for a in actions:
            if a.text() == 'Customize':
                self.toolbar.removeAction(a)
                break
        self.mplvl.addWidget(self.toolbar)
        self.canvas.draw()

        # CREATE MODELS
        # Create phasemodel and define some logic
        self.phasemodel = QtGui.QStandardItemModel(self.phaseview)
        self.phaseview.setModel(self.phasemodel)
        self.phaseview.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.phaseview.show()
        # Create outmodel
        self.outmodel = QtGui.QStandardItemModel(self.outview)
        self.outview.setModel(self.outmodel)
        self.outview.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.outview.show()

        # SET PT RANGE VALIDATORS
        validator = QtGui.QDoubleValidator()
        validator.setLocale(QtCore.QLocale.c())
        self.tminEdit.setValidator(validator)
        self.tminEdit.textChanged.connect(self.check_validity)
        self.tminEdit.textChanged.emit(self.tminEdit.text())
        self.tmaxEdit.setValidator(validator)
        self.tmaxEdit.textChanged.connect(self.check_validity)
        self.tmaxEdit.textChanged.emit(self.tmaxEdit.text())
        self.pminEdit.setValidator(validator)
        self.pminEdit.textChanged.connect(self.check_validity)
        self.pminEdit.textChanged.emit(self.pminEdit.text())
        self.pmaxEdit.setValidator(validator)
        self.pmaxEdit.textChanged.connect(self.check_validity)
        self.pmaxEdit.textChanged.emit(self.pmaxEdit.text())

        # SET OUTPUT TEXT FIXED FONTS
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.textOutput.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.textOutput.setReadOnly(True)
        self.textOutput.setFont(f)
        self.textFullOutput.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.textFullOutput.setReadOnly(True)
        self.textFullOutput.setFont(f)
        self.outScript.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.outScript.setFont(f)
        self.logDogmin.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.logDogmin.setReadOnly(True)
        self.logDogmin.setFont(f)
        self.logText.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.logText.setReadOnly(True)
        self.logText.setFont(f)

        self.initViewModels()

        # CONNECT SIGNALS
        self.actionNew.triggered.connect(self.initProject)
        self.actionOpen.triggered.connect(self.openProject)
        self.actionSave.triggered.connect(self.saveProject)
        self.actionSave_as.triggered.connect(self.saveProjectAs)
        self.actionQuit.triggered.connect(self.close)
        # self.actionExport_Drawpd.triggered.connect(self.gendrawpd)
        self.actionAbout.triggered.connect(self.about_dialog.exec)
        self.actionImport_project.triggered.connect(self.import_from_prj)
        self.actionShow_areas.triggered.connect(self.check_prj_areas)
        self.actionShow_topology.triggered.connect(self.show_topology)
        self.pushCalcTatP.clicked.connect(lambda: self.do_calc(True))
        self.pushCalcPatT.clicked.connect(lambda: self.do_calc(False))
        self.pushApplySettings.clicked.connect(lambda: self.apply_setting(5))
        self.pushResetSettings.clicked.connect(lambda: self.apply_setting(8))
        self.pushFromAxes.clicked.connect(lambda: self.apply_setting(2))
        self.tabMain.currentChanged.connect(lambda: self.apply_setting(4))
        self.pushReadScript.clicked.connect(self.read_scriptfile)
        self.pushSaveScript.clicked.connect(self.save_scriptfile)
        self.actionReload.triggered.connect(self.reinitialize)
        self.actionGenerate.triggered.connect(self.generate)
        self.pushGuessUni.clicked.connect(self.unisel_guesses)
        self.pushGuessInv.clicked.connect(self.invsel_guesses)
        self.pushInvAuto.clicked.connect(self.auto_inv_calc)
        self.pushUniSearch.clicked.connect(self.uni_explore)
        self.pushManual.toggled.connect(self.add_userdefined)
        self.pushManual.setCheckable(True)
        self.pushDogmin.toggled.connect(self.do_dogmin)
        self.pushDogmin.setCheckable(True)
        self.pushDogmin_select.clicked.connect(self.dogmin_select_phases)
        self.pushDogmin_guesses.clicked.connect(self.dogmin_set_guesses)
        self.pushInvRemove.clicked.connect(self.remove_inv)
        self.pushUniRemove.clicked.connect(self.remove_uni)
        self.tabOutput.tabBarDoubleClicked.connect(self.show_output)
        self.splitter_bottom.setSizes((400, 100))

        self.phaseview.doubleClicked.connect(self.show_out)
        self.uniview.doubleClicked.connect(self.show_uni)
        self.uniview.customContextMenuRequested[QtCore.QPoint].connect(self.univiewRightClicked)
        self.invview.doubleClicked.connect(self.show_inv)
        self.invview.customContextMenuRequested[QtCore.QPoint].connect(self.invviewRightClicked)
        # additional keyboard shortcuts
        self.scCalcTatP = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.scCalcTatP.activated.connect(lambda: self.do_calc(True))
        self.scCalcPatT = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)
        self.scCalcPatT.activated.connect(lambda: self.do_calc(False))
        self.scHome = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+H"), self)
        self.scHome.activated.connect(self.toolbar.home)
        self.showAreas = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+A"), self)
        self.showAreas.activated.connect(self.check_prj_areas)

        self.app_settings()
        self.populate_recent()
        self.ready = False
        self.project = None
        self.statusBar().showMessage('PSBuilder version {} (c) Ondrej Lexa 2020'. format(__version__))

    def initViewModels(self):
        # INVVIEW
        self.invmodel = InvModel(self.invview)
        self.invview.setModel(self.invmodel)
        # enable sorting
        self.invview.setSortingEnabled(False)
        # hide column
        self.invview.setColumnHidden(2, True)
        # select rows
        self.invview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.invview.horizontalHeader().setMinimumSectionSize(40)
        self.invview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.invview.horizontalHeader().hide()
        self.invsel = self.invview.selectionModel()
        # default unconnected ghost
        self.invmodel.appendRow([0, 'Unconnected', {}])
        self.invview.setRowHidden(0, True)
        self.invview.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # signals
        self.invsel.selectionChanged.connect(self.sel_changed)

        # UNIVIEW
        self.unimodel = UniModel(self.uniview)
        self.uniview.setModel(self.unimodel)
        # enable sorting
        self.uniview.setSortingEnabled(False)
        # hide column
        self.uniview.setColumnHidden(4, True)
        self.uniview.setItemDelegateForColumn(2, ComboDelegate(self, self.invmodel, self.checkStrict))
        self.uniview.setItemDelegateForColumn(3, ComboDelegate(self, self.invmodel, self.checkStrict))
        # select rows
        self.uniview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.uniview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.uniview.horizontalHeader().setMinimumSectionSize(40)
        self.uniview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.uniview.horizontalHeader().hide()
        # edit trigger
        self.uniview.setEditTriggers(QtWidgets.QAbstractItemView.CurrentChanged | QtWidgets.QAbstractItemView.SelectedClicked)
        self.uniview.viewport().installEventFilter(self)
        self.uniview.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # signals
        self.unimodel.dataChanged.connect(self.uni_edited)
        self.unisel = self.uniview.selectionModel()
        self.unisel.selectionChanged.connect(self.sel_changed)

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'pypsbuilder')
        if write:
            builder_settings.setValue("steps", self.spinSteps.value())
            builder_settings.setValue("precision", self.spinPrec.value())
            builder_settings.setValue("extend_range", self.spinOver.value())
            builder_settings.setValue("dogmin_level", self.spinDoglevel.value())
            builder_settings.setValue("label_uni", self.checkLabelUni.checkState())
            builder_settings.setValue("label_uni_text", self.checkLabelUniText.checkState())
            builder_settings.setValue("label_inv", self.checkLabelInv.checkState())
            builder_settings.setValue("label_inv_text", self.checkLabelInvText.checkState())
            builder_settings.setValue("dot_inv", self.checkDotInv.checkState())
            builder_settings.setValue("label_alpha", self.spinAlpha.value())
            builder_settings.setValue("label_fontsize", self.spinFontsize.value())
            builder_settings.setValue("strict_filtering", self.checkStrict.checkState())
            builder_settings.setValue("autoconnectuni", self.checkAutoconnectUni.checkState())
            builder_settings.setValue("autoconnectinv", self.checkAutoconnectInv.checkState())
            # builder_settings.setValue("export_areas", self.checkAreas.checkState())
            # builder_settings.setValue("export_partial", self.checkPartial.checkState())
            builder_settings.setValue("overwrite", self.checkOverwrite.checkState())
            builder_settings.beginWriteArray("recent")
            for ix, f in enumerate(self.recent):
                builder_settings.setArrayIndex(ix)
                builder_settings.setValue("projfile", f)
            builder_settings.endArray()
        else:
            self.spinSteps.setValue(builder_settings.value("steps", 50, type=int))
            self.spinPrec.setValue(builder_settings.value("precision", 1, type=int))
            self.spinOver.setValue(builder_settings.value("extend_range", 5, type=int))
            self.spinDoglevel.setValue(builder_settings.value("dogmin_level", 1, type=int))
            self.checkLabelUni.setCheckState(builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelUniText.setCheckState(builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelInv.setCheckState(builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelInvText.setCheckState(builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkDotInv.setCheckState(builder_settings.value("dot_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkStrict.setCheckState(builder_settings.value("strict_filtering", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkAutoconnectUni.setCheckState(builder_settings.value("autoconnectuni", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkAutoconnectInv.setCheckState(builder_settings.value("autoconnectinv", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            # self.checkAreas.setCheckState(builder_settings.value("export_areas", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            # self.checkPartial.setCheckState(builder_settings.value("export_partial", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkOverwrite.setCheckState(builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                self.recent.append(builder_settings.value("projfile", type=str))
            builder_settings.endArray()

    def populate_recent(self):
        self.menuOpen_recent.clear()
        for f in self.recent:
            self.menuOpen_recent.addAction(Path(f).name, lambda f=f: self.openProject(False, projfile=f))

    def initProject(self):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        workdir = qd.getExistingDirectory(self, "Select Directory",
                                          os.path.expanduser('~'),
                                          qd.ShowDirsOnly)
        if workdir:
            prj = TCAPI(workdir)
            if prj.OK:
                self.prj = prj
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', prj.status, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save,
                                qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Open project',
                                          os.path.expanduser('~'),
                                          'pypsbuilder project (*.psb)')[0]
        if Path(projfile).is_file():
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            if data.get('version', '1.0.0') < '2.1.0':
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Old version',
                            'This project is created in older version.\nUse import from project.',
                            qb.Abort)
            else:
                prj = TCAPI(data.get('workdir', Path(projfile).resolve().parent))
                if prj.OK:
                    self.prj = prj
                    self.refresh_gui()
                    self.initViewModels()
                    # select phases
                    for i in range(self.phasemodel.rowCount()):
                        item = self.phasemodel.item(i)
                        if item.text() in data['selphases']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # select out
                    for i in range(self.outmodel.rowCount()):
                        item = self.outmodel.item(i)
                        if item.text() in data['out']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # settings
                    self.prj.trange = data['trange']
                    self.prj.prange = data['prange']
                    # views
                    for row in data['unilist']:
                        self.unimodel.appendRow(row)
                    self.uniview.resizeColumnsToContents()
                    for row in data['invlist']:
                        self.invmodel.appendRow(row)
                    self.invview.resizeColumnsToContents()
                    # cutting
                    for row in self.unimodel.unilist:
                        self.trimuni(row)
                    # all done
                    self.ready = True
                    self.project = projfile
                    self.changed = False
                    if projfile in self.recent:
                        self.recent.pop(self.recent.index(projfile))
                    self.recent.insert(0, projfile)
                    if len(self.recent) > 15:
                        self.recent = self.recent[:15]
                    self.populate_recent()
                    self.app_settings(write=True)
                    # read scriptfile
                    self.read_scriptfile()
                    # update settings tab
                    self.apply_setting(4)
                    # update plot
                    self.figure.clear()
                    self.plot()
                    self.statusBar().showMessage('Project loaded.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', prj.status, qb.Abort)
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

    def import_from_prj(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Import from project', str(self.prj.workdir),
                                          'pypsbuilder project (*.psb)')[0]
            if Path(projfile).exists():
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                with gzip.open(projfile, 'rb') as stream:
                    data = pickle.load(stream)
                # do import
                self.initViewModels()
                # select phases
                for i in range(self.phasemodel.rowCount()):
                    item = self.phasemodel.item(i)
                    if item.text() in data['selphases']:
                        item.setCheckState(QtCore.Qt.Checked)
                # select out
                for i in range(self.outmodel.rowCount()):
                    item = self.outmodel.item(i)
                    if item.text() in data['out']:
                        item.setCheckState(QtCore.Qt.Checked)
                # settings
                self.prj.trange = data['trange']
                self.prj.prange = data['prange']
                # Import
                for row in data['invlist']:
                    row[2]['phases'] = row[2]['phases'].union(self.prj.excess)
                    r = dict(phases=row[2]['phases'], out=row[2]['out'],
                             cmd=row[2].get('cmd', ''), variance=-1,
                             p=row[2]['p'], T=row[2]['T'], manual=True,
                             output='Imported invariant point.')
                    label = self.format_label(row[2]['phases'], row[2]['out'])
                    self.invmodel.appendRow((row[0], label, r))
                self.invview.resizeColumnsToContents()
                for row in data['unilist']:
                    row[4]['phases'] = row[4]['phases'].union(self.prj.excess)
                    r = dict(phases=row[4]['phases'], out=row[4]['out'],
                             cmd=row[4].get('cmd', ''), variance=-1,
                             p=row[4]['p'], T=row[4]['T'], manual=True,
                             output='Imported univariant line.')
                    label = self.format_label(row[4]['phases'], row[4]['out'])
                    self.unimodel.appendRow((row[0], label, row[2], row[3], r))
                self.uniview.resizeColumnsToContents()
                # # try to recalc
                progress = QtWidgets.QProgressDialog("Recalculate inv points", "Cancel",
                                                     0, len(data['invlist']), self)
                progress.setWindowModality(QtCore.Qt.WindowModal)
                progress.setMinimumDuration(0)
                old_guesses = self.prj.update_scriptfile(get_old_guesses=True)
                for ix, row in enumerate(data['invlist']):
                    progress.setValue(ix)
                    if 'cmd' in row[2]:
                        if row[2]['cmd']:
                            self.prj.update_scriptfile(guesses=row[2]['results'][0]['ptguess'])
                            tcout = self.prj.runtc(row[2]['cmd'])
                            status, variance, pts, res, output = self.prj.parse_logfile()
                            if status == 'ok':
                                r = dict(phases=row[2]['phases'], out=row[2]['out'], cmd=row[2]['cmd'],
                                         variance=variance, p=pts[0], T=pts[1], manual=False,
                                         output=output, results=res)
                                label = self.format_label(row[2]['phases'], row[2]['out'])
                                isnew, id = self.getidinv(r)
                                urow = self.invmodel.getRowFromId(id)
                                urow[1] = label
                                urow[2] = r
                    if progress.wasCanceled():
                        break
                progress.setValue(len(data['invlist']))
                progress.deleteLater()
                self.invview.resizeColumnsToContents()
                progress = QtWidgets.QProgressDialog("Recalculate uni lines", "Cancel",
                                                     0, len(data['unilist']), self)
                progress.setWindowModality(QtCore.Qt.WindowModal)
                progress.setMinimumDuration(0)
                for ix, row in enumerate(data['unilist']):
                    progress.setValue(ix)
                    if 'cmd' in row[4]:
                        if row[4]['cmd']:
                            midix = len(row[4]['results']) // 2
                            self.prj.update_scriptfile(guesses=row[4]['results'][midix]['ptguess'])
                            tcout = self.prj.runtc(row[4]['cmd'])
                            status, variance, pts, res, output = self.prj.parse_logfile()
                            if status == 'ok' and len(res) > 1:
                                r = dict(phases=row[4]['phases'], out=row[4]['out'], cmd=row[4]['cmd'],
                                         variance=variance, p=pts[0], T=pts[1], manual=False,
                                         output=output, results=res)
                                label = self.format_label(row[4]['phases'], row[4]['out'])
                                isnew, id = self.getiduni(r)
                                urow = self.unimodel.getRowFromId(id)
                                urow[1] = label
                                urow[4] = r
                    if progress.wasCanceled():
                        break
                progress.setValue(len(data['unilist']))
                progress.deleteLater()
                self.uniview.resizeColumnsToContents()
                self.prj.update_scriptfile(guesses=old_guesses)
                # cutting
                for row in self.unimodel.unilist:
                    self.trimuni(row)
                # all done
                self.changed = True
                self.app_settings(write=True)
                # read scriptfile
                self.read_scriptfile()
                # update settings tab
                self.apply_setting(4)
                # update plot
                self.figure.clear()
                self.plot()
                self.statusBar().showMessage('Project Imported.')
                QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def refresh_gui(self):
        # update settings tab
        self.apply_setting(4)
        # read scriptfile
        self.read_scriptfile()
        # update plot
        self.figure.clear()
        self.plot()
        # disconnect signals
        try:
            self.phasemodel.itemChanged.disconnect(self.phase_changed)
        except Exception:
            pass
        self.logText.setPlainText('Working directory:{}\n\n'.format(self.prj.workdir) + self.prj.tcout)
        self.phasemodel.clear()
        self.outmodel.clear()
        for p in self.prj.phases:
            if p not in self.prj.excess:
                item = QtGui.QStandardItem(p)
                item.setCheckable(True)
                item.setSizeHint(QtCore.QSize(40, 20))
                self.phasemodel.appendRow(item)
        # connect signal
        self.phasemodel.itemChanged.connect(self.phase_changed)
        self.textOutput.clear()
        self.textFullOutput.clear()
        self.unihigh = None
        self.invhigh = None
        self.outhigh = None
        self.statusBar().showMessage('Ready')

    def reinitialize(self):
        if self.ready:
            # collect info
            phases = []
            for i in range(self.phasemodel.rowCount()):
                item = self.phasemodel.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    phases.append(item.text())
            out = []
            for i in range(self.outmodel.rowCount()):
                item = self.outmodel.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    out.append(item.text())
            trange = self.prj.trange
            prange = self.prj.prange
            # reread
            prj = TCAPI(self.prj.workdir)
            if prj.OK:
                self.prj = prj
                # select phases
                for i in range(self.phasemodel.rowCount()):
                    item = self.phasemodel.item(i)
                    if item.text() in phases:
                        item.setCheckState(QtCore.Qt.Checked)
                # select out
                for i in range(self.outmodel.rowCount()):
                    item = self.outmodel.item(i)
                    if item.text() in out:
                        item.setCheckState(QtCore.Qt.Checked)
                # adapt names to excess changes
                for row in self.unimodel.unilist:
                    row[1] = (' '.join(sorted(list(row[4]['phases'].difference(self.prj.excess)))) +
                              ' - ' +
                              ' '.join(sorted(list(row[4]['out']))))
                self.uniview.resizeColumnsToContents()
                for row in self.invmodel.invlist[1:]:
                    row[1] = (' '.join(sorted(list(row[2]['phases'].difference(self.prj.excess)))) +
                              ' - ' +
                              ' '.join(sorted(list(row[2]['out']))))
                self.invview.resizeColumnsToContents()
                # settings
                self.prj.trange = trange
                self.prj.prange = prange
                self.refresh_gui()
                self.statusBar().showMessage('Project re-initialized from scriptfile.')
                self.changed = True
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', prj.status, qb.Abort)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def saveProject(self):
        """Open working directory and initialize project
        """
        if self.ready:
            if self.project is None:
                filename = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project', str(self.prj.workdir), 'pypsbuilder project (*.psb)')[0]
                if filename:
                    if not filename.lower().endswith('.psb'):
                        filename = filename + '.psb'
                    self.project = filename
                    self.do_save()
            else:
                self.do_save()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def saveProjectAs(self):
        """Open working directory and initialize project
        """
        if self.ready:
            filename = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project as', str(self.prj.workdir), 'pypsbuilder project (*.psb)')[0]
            if filename:
                if not filename.lower().endswith('.psb'):
                    filename = filename + '.psb'
                self.project = filename
                self.do_save()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    @property
    def data(self):
        # collect info
        selphases = []
        for i in range(self.phasemodel.rowCount()):
            item = self.phasemodel.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selphases.append(item.text())
        out = []
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                out.append(item.text())
        # put to dict
        data = {'selphases': selphases,
                'out': out,
                'trange': self.prj.trange,
                'prange': self.prj.prange,
                'unilist': self.unimodel.unilist.copy(),
                'invlist': self.invmodel.invlist[1:].copy(),
                'tcversion': self.prj.tcversion,
                'workdir': self.prj.workdir,
                'uuid': str(uuid.uuid4()),
                'version': __version__}
        return data

    def do_save(self):
        """Open working directory and initialize project
        """
        if self.project is not None:
            # do save
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            with gzip.open(self.project, 'wb') as stream:
                pickle.dump(self.data, stream)
            self.changed = False
            if self.project in self.recent:
                self.recent.pop(self.recent.index(self.project))
            self.recent.insert(0, self.project)
            if len(self.recent) > 15:
                self.recent = self.recent[:15]
            self.populate_recent()
            self.app_settings(write=True)
            self.statusBar().showMessage('Project saved.')
            QtWidgets.QApplication.restoreOverrideCursor()

    def reparse_outputs(self):
        for row in data['invlist']:
            status, variance, pts, res, output = self.prj.parse_logfile(output=row[2]['output'])
            if status == 'ok':
                r = dict(phases=row[2]['phases'], out=row[2]['out'], cmd=row[2]['cmd'],
                         variance=variance, p=pts[0], T=pts[1], manual=False,
                         output=output, results=res)
                label = self.format_label(row[2]['phases'], row[2]['out'])
                isnew, id = self.getidinv(r)
                urow = self.invmodel.getRowFromId(id)
                urow[1] = label
                urow[2] = r
        self.invview.resizeColumnsToContents()
        for row in data['unilist']:
            status, variance, pts, res, output = self.prj.parse_logfile(output=row[4]['output'])
            if status == 'ok':
                r = dict(phases=row[4]['phases'], out=row[4]['out'], cmd=row[4]['cmd'],
                         variance=variance, p=pts[0], T=pts[1], manual=False,
                         output=output, results=res)
                label = self.format_label(row[4]['phases'], row[4]['out'])
                isnew, id = self.getiduni(r)
                urow = self.unimodel.getRowFromId(id)
                urow[1] = label
                urow[4] = r
        self.uniview.resizeColumnsToContents()
        self.statusBar().showMessage('Outputs re-parsed.')
        self.changed = True

    def generate(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            tpfile = qd.getOpenFileName(self, 'Open drawpd file', str(self.prj.workdir),
                                        'Drawpd files (*.txt);;All files (*.*)')[0]
            if tpfile:
                tp = []
                tpok = True
                with open(tpfile, 'r', encoding=self.prj.TCenc) as tfile:
                    for line in tfile:
                        n = line.split('%')[0].strip()
                        if n != '':
                            if '-' in n:
                                if n.startswith('i') or n.startswith('u'):
                                    tp.append(n.split(' ', 1)[1].strip())
                if tpok and tp:
                    for r in tp:
                        po = r.split('-')
                        out = set(po[1].split())
                        phases = set(po[0].split()).union(out).union(self.prj.excess)
                        self.do_calc(True, phases=phases, out=out)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    @property
    def changed(self):
        return self.__changed

    @changed.setter
    def changed(self, status):
        self.__changed = status
        if self.project is None:
            title = 'PSbuilder - New project - {}'.format(self.prj.tcversion)
        else:
            title = 'PSbuilder - {} - {}'.format(Path(self.project).name, self.prj.tcversion)
        if status:
            title += '*'
        self.setWindowTitle(title)

    def format_coord(self, x, y):
        prec = self.spinPrec.value()
        return 'T={:.{prec}f} p={:.{prec}f}'.format(x, y, prec=prec)

    def show_output(self, int):
        if self.ready:
            if int == 0:
                dia = OutputDialog('Modes', self.textOutput.toPlainText())
                dia.exec()
            if int == 1:
                dia = OutputDialog('TC output', self.textFullOutput.toPlainText())
                dia.exec()

    def clean_high(self):
        if self.unihigh is not None:
            try:
                self.unihigh[0].remove()
            except:
                pass
            self.unihigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
            self.canvas.draw()
        if self.invhigh is not None:
            try:
                self.invhigh[0].remove()
            except:
                pass
            self.invhigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
            self.canvas.draw()
        if self.outhigh is not None:
            try:
                self.outhigh[0].remove()
            except:
                pass
            self.outhigh = None
            self.canvas.draw()

    def sel_changed(self):
        self.clean_high()

    def invsel_guesses(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            if not r['manual']:
                self.prj.update_scriptfile(guesses=r['results'][0]['ptguess'])
                self.read_scriptfile()
                self.statusBar().showMessage('Invariant point ptuess set.')
            else:
                self.statusBar().showMessage('Guesses cannot be set from user-defined invariant point.')

    def unisel_guesses(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            r = self.unimodel.data(idx[4])
            if not r['manual']:
                lbl = ['p = {}, T = {}'.format(p, T) for p, T in zip(r['p'], r['T'])]
                uniguess = UniGuess(lbl, self)
                respond = uniguess.exec()
                if respond == QtWidgets.QDialog.Accepted:
                    ix = uniguess.getValue()
                    self.prj.update_scriptfile(guesses=r['results'][ix]['ptguess'])
                    self.read_scriptfile()
                    self.statusBar().showMessage('Univariant line ptguess set.')
            else:
                self.statusBar().showMessage('Guesses cannot be set from user-defined univariant line.')

    def get_phases_out(self):
        phases = []
        for i in range(self.phasemodel.rowCount()):
                item = self.phasemodel.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    phases.append(item.text())
        out = []
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                out.append(item.text())
        return set(phases).union(self.prj.excess), set(out)

    def set_phaselist(self, r, show_output=True):
        for i in range(self.phasemodel.rowCount()):
            item = self.phasemodel.item(i)
            if item.text() in r['phases'] or item.text() in r['out']:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        # select out
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.text() in r['out']:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        if show_output:
            if not r['manual']:
                txt = ''
                mlabels = sorted(list(r['phases'].difference(self.prj.excess)))
                h_format = '{:>10}{:>10}' + '{:>8}' * len(mlabels)
                n_format = '{:10.4f}{:10.4f}' + '{:8.5f}' * len(mlabels)
                txt += h_format.format('p', 'T', *mlabels)
                txt += '\n'
                for p, T, res in zip(r['p'], r['T'], r['results']):
                    row = [p, T] + [res['data'][lbl]['mode'] for lbl in mlabels]
                    txt += n_format.format(*row)
                    txt += '\n'
                if len(r['results']) > 5:
                    txt += h_format.format('p', 'T', *mlabels)
                self.textOutput.setPlainText(txt)
            else:
                self.textOutput.setPlainText(r['output'])
            self.textFullOutput.setPlainText(r['output'])

    def show_uni(self, index):
        row = self.unimodel.getRow(index)
        self.clean_high()
        self.set_phaselist(row[4], show_output=True)
        T, p = self.get_trimmed_uni(row)
        self.unihigh = self.ax.plot(T, p, '-', **unihigh_kw)
        self.canvas.draw()

    def uni_edited(self, index):
        row = self.unimodel.getRow(index)
        # self.set_phaselist(row[4])
        self.trimuni(row)
        self.changed = True
        # update plot
        self.plot()

    def uni_explore(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            r = self.unimodel.data(idx[4])
            phases = r['phases']
            out = r['out']
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily
            midix = len(r['results']) // 2
            old_guesses = self.prj.update_scriptfile(guesses=r['results'][midix]['ptguess'], get_old_guesses=True)
            # Try out from phases
            cand = []
            for ophase in phases.difference(out).difference(self.prj.excess):
                nout = out.union(set([ophase]))
                self.prj.tc_calc_pt(phases, nout)
                status, variance, pts, res, output = self.prj.parse_logfile()
                if status == 'ok':
                    p, T = pts.flatten()
                    ix = ((r['p'] - p)**2 + (r['T'] - T)**2).argmin()
                    exists, inv_id = '', ''
                    for row in self.invmodel.invlist[1:]:
                        if phases == row[2]['phases'] and nout == row[2]['out']:
                            exists, inv_id = '*', str(row[0])
                            break
                    cand.append([ix, p, T, exists, ' '.join(nout), inv_id])

            for ophase in set(self.prj.phases).difference(self.prj.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.prj.tc_calc_pt(nphases, nout)
                status, variance, pts, res, output = self.prj.parse_logfile()
                if status == 'ok':
                    p, T = pts.flatten()
                    ix = ((r['p'] - p)**2 + (r['T'] - T)**2).argmin()
                    exists, inv_id = '', ''
                    for row in self.invmodel.invlist[1:]:
                        if nphases == row[2]['phases'] and nout == row[2]['out']:
                            exists, inv_id = '*', str(row[0])
                            break
                    cand.append([ix, p, T, exists, ' '.join(nout), inv_id])

            self.prj.update_scriptfile(guesses=old_guesses)
            QtWidgets.QApplication.restoreOverrideCursor()
            if cand:
                txt = '         p         T E     Out   Inv\n'
                n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
                for cc in sorted(cand):
                    txt += n_format.format(*cc[1:])

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            else:
                self.statusBar().showMessage('No invariant points found.')

    def show_inv(self, index):
        dt = self.invmodel.getData(index, 'Data')
        self.clean_high()
        self.set_phaselist(dt, show_output=True)
        self.invhigh = self.ax.plot(dt['T'], dt['p'], 'o', **invhigh_kw)
        self.canvas.draw()

    def show_out(self, index):
        out = self.phasemodel.itemFromIndex(index).text()
        self.clean_high()
        oT = []
        op = []
        for r in self.unimodel.unilist:
            if out in r[4]['out']:
                T, p = self.get_trimmed_uni(r)
                oT.append(T)
                oT.append([np.nan])
                op.append(p)
                op.append([np.nan])
        if oT:
            self.outhigh = self.ax.plot(np.concatenate(oT), np.concatenate(op),
                                        '-', **outhigh_kw)
            self.canvas.draw()

    def invviewRightClicked(self, QPos):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            phases = r['phases']
            out = r['out']
            a, b = out
            aset, bset = set([a]), set([b])
            aphases, bphases = phases.difference(aset), phases.difference(bset)
            show_menu = False
            menu = QtWidgets.QMenu(self)
            # Check for polymorphs
            fix = False
            for poly in polymorphs:
                if poly.issubset(phases):
                    fix = True
                    break
            if fix:
                if poly != out: # on boundary
                    nopoly = out.difference(poly.intersection(out))
                    aphases = phases.difference(poly.intersection(out))
                    bphases = phases.difference(poly.difference(out))

                    nr1 = dict(phases=aphases, out=nopoly, output='User-defined')
                    lbl1 = ' '.join(sorted(list(nr1['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr1['out'])
                    isnew, id = self.getiduni(nr1)
                    if isnew:
                        menu_item1 = menu.addAction(lbl1)
                        menu_item1.triggered.connect(lambda: self.set_phaselist(nr1, show_output=False))
                        show_menu = True
                    nr2 = dict(phases=bphases, out=nopoly, output='User-defined')
                    lbl2 = ' '.join(sorted(list(nr2['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr2['out'])
                    isnew, id = self.getiduni(nr2)
                    if isnew:
                        menu_item2 = menu.addAction(lbl2)
                        menu_item2.triggered.connect(lambda: self.set_phaselist(nr2, show_output=False))
                        show_menu = True
                    nr3 = dict(phases=phases, out=poly.intersection(out), output='User-defined')
                    lbl3 = ' '.join(sorted(list(nr3['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr3['out'])
                    isnew, id = self.getiduni(nr3)
                    if isnew:
                        menu_item3 = menu.addAction(lbl3)
                        menu_item3.triggered.connect(lambda: self.set_phaselist(nr3, show_output=False))
                        show_menu = True
                    nr4 = dict(phases=phases.difference(nopoly), out=poly.intersection(out), output='User-defined')
                    lbl4 = ' '.join(sorted(list(nr4['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr4['out'])
                    isnew, id = self.getiduni(nr4)
                    if isnew:
                        menu_item4 = menu.addAction(lbl4)
                        menu_item4.triggered.connect(lambda: self.set_phaselist(nr4, show_output=False))
                        show_menu = True
                else:           # triple point  NEED FIX
                    nr1 = dict(phases=phases, out=aset, output='User-defined')
                    lbl1 = ' '.join(sorted(list(nr1['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr1['out'])
                    isnewa, id = self.getiduni(nr1)
                    nr1 = dict(phases=phases, out=bset, output='User-defined')
                    lbl1 = ' '.join(sorted(list(nr1['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr1['out'])
                    isnewb, id = self.getiduni(nr1)
                    if isnewa and isnewb:
                        menu_item1 = menu.addAction(lbl1)
                        menu_item1.triggered.connect(lambda: self.set_phaselist(nr1, show_output=False))
                        show_menu = True
                    nr2 = dict(phases=aphases, out=bset, output='User-defined')
                    lbl2 = ' '.join(sorted(list(nr2['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr2['out'])
                    isnew, id = self.getiduni(nr2)
                    if isnew:
                        menu_item2 = menu.addAction(lbl2)
                        menu_item2.triggered.connect(lambda: self.set_phaselist(nr2, show_output=False))
                        show_menu = True
                    nr3 = dict(phases=bphases, out=aset, output='User-defined')
                    lbl3 = ' '.join(sorted(list(nr3['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr3['out'])
                    isnew, id = self.getiduni(nr3)
                    if isnew:
                        menu_item3 = menu.addAction(lbl3)
                        menu_item3.triggered.connect(lambda: self.set_phaselist(nr3, show_output=False))
                        show_menu = True
            else:
                nr1 = dict(phases=phases, out=aset, output='User-defined')
                lbl1 = ' '.join(sorted(list(nr1['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr1['out'])
                isnew, id = self.getiduni(nr1)
                if isnew:
                    menu_item1 = menu.addAction(lbl1)
                    menu_item1.triggered.connect(lambda: self.set_phaselist(nr1, show_output=False))
                    show_menu = True
                nr2 = dict(phases=phases, out=bset, output='User-defined')
                lbl2 = ' '.join(sorted(list(nr2['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr2['out'])
                isnew, id = self.getiduni(nr2)
                if isnew:
                    menu_item2 = menu.addAction(lbl2)
                    menu_item2.triggered.connect(lambda: self.set_phaselist(nr2, show_output=False))
                    show_menu = True
                nr3 = dict(phases=bphases, out=aset, output='User-defined')
                lbl3 = ' '.join(sorted(list(nr3['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr3['out'])
                isnew, id = self.getiduni(nr3)
                if isnew:
                    menu_item3 = menu.addAction(lbl3)
                    menu_item3.triggered.connect(lambda: self.set_phaselist(nr3, show_output=False))
                    show_menu = True
                nr4 = dict(phases=aphases, out=bset, output='User-defined')
                lbl4 = ' '.join(sorted(list(nr4['phases'].difference(self.prj.excess)))) + ' - ' + ' '.join(nr4['out'])
                isnew, id = self.getiduni(nr4)
                if isnew:
                    menu_item4 = menu.addAction(lbl4)
                    menu_item4.triggered.connect(lambda: self.set_phaselist(nr4, show_output=False))
                    show_menu = True
            if show_menu:
                menu.exec(self.invview.mapToGlobal(QPos))

    def univiewRightClicked(self, QPos):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            r = self.unimodel.getRow(idx[4])
            #phases = r[4]['phases']
            #out = r[4]['out']
            menu = QtWidgets.QMenu(self)
            menu_item1 = menu.addAction('Zoom')
            menu_item1.triggered.connect(lambda: self.zoom_to_uni(r))
            be = r[2:4]
            miss = be.count(0)
            if miss > 0:
                candidates = []
                for invrow in self.invmodel.invlist[1:]:
                    if (invrow[0] not in be) and inv_on_uni(r[4]['phases'], r[4]['out'], invrow[2]['phases'], invrow[2]['out']):
                        candidates.append(invrow[0])
                        # iphases = invrow[2]['phases']
                        # iout = invrow[2]['out']
                        # a, b = iout
                        # aset, bset = set([a]), set([b])
                        # aphases, bphases = iphases.difference(aset), iphases.difference(bset)
                        # if iphases == phases and len(iout.difference(out)) == 1:
                        #     candidates.append(invrow[0])
                        # elif bphases == phases and aset == out:
                        #     candidates.append(invrow[0])
                        # elif aphases == phases and bset == out:
                        #     candidates.append(invrow[0])
                if len(candidates) == miss:
                    menu_item2 = menu.addAction('Autoconnect')
                    menu_item2.triggered.connect(lambda: self.auto_connect(r, candidates, idx))
            menu.exec(self.uniview.mapToGlobal(QPos))

    def auto_connect(self, r, candidates, idx):
        if len(candidates) == 1:
            if r[2] == 0:
                self.unimodel.setData(idx[2], candidates[0])
            else:
                self.unimodel.setData(idx[3], candidates[0])
        else:
            ratio = (self.prj.trange[1] - self.prj.trange[0]) / (self.prj.prange[1] - self.prj.prange[0])
            xy = np.array([r[4]['T'], ratio * r[4]['p']]).T
            line = LineString(xy)
            dt = self.invmodel.getDataFromId(candidates[0])
            p0 = Point(dt['T'][0], ratio * dt['p'][0])
            dt = self.invmodel.getDataFromId(candidates[1])
            p1 = Point(dt['T'][0], ratio * dt['p'][0])
            d0 = line.project(p0)
            d1 = line.project(p1)
            if d0 < d1:
                self.unimodel.setData(idx[2], candidates[0])
                self.unimodel.setData(idx[3], candidates[1])
            else:
                self.unimodel.setData(idx[2], candidates[1])
                self.unimodel.setData(idx[3], candidates[0])

    def auto_add_uni(self, phases, out):
        nr = dict(phases=phases, out=out, output='User-defined')
        isnew, id = self.getiduni(nr)
        if isnew:
            self.do_calc(True, phases=nr['phases'], out=nr['out'])
        isnew, id = self.getiduni(nr)
        if isnew:
            self.do_calc(False, phases=nr['phases'], out=nr['out'])

    def auto_inv_calc(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            self.statusBar().showMessage('Running auto univariant lines calculations...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            self.prj.update_scriptfile(guesses=r['results'][0]['ptguess'])
            phases = r['phases']
            out = r['out']
            a, b = out
            aset, bset = set([a]), set([b])
            aphases, bphases = phases.difference(aset), phases.difference(bset)
            fix = False
            for poly in polymorphs:
                if poly.issubset(phases):
                    fix = True
                    break
            if fix:
                if poly != out: # on boudary
                    nopoly = out.difference(poly.intersection(out))
                    aphases = phases.difference(poly.intersection(out))
                    bphases = phases.difference(poly.difference(out))
                    self.auto_add_uni(aphases, nopoly)
                    self.auto_add_uni(bphases, nopoly)
                    self.auto_add_uni(phases, poly.intersection(out))
                    self.auto_add_uni(phases.difference(nopoly), poly.intersection(out))
                else:     # triple point  NEED FIX
                    nr1 = dict(phases=phases, out=aset, output='User-defined')
                    isnewa, id = self.getiduni(nr1)
                    nr1 = dict(phases=phases, out=bset, output='User-defined')
                    isnewb, id = self.getiduni(nr1)
                    if isnewa and isnewb:
                        self.auto_add_uni(phases, bset)

                    self.auto_add_uni(aphases, bset)
                    self.auto_add_uni(bphases, aset)
            else:
                self.auto_add_uni(phases, aset)
                self.auto_add_uni(phases, bset)
                self.auto_add_uni(bphases, aset)
                self.auto_add_uni(aphases, bset)

            self.read_scriptfile()
            self.clean_high()
            QtWidgets.QApplication.restoreOverrideCursor()
            self.statusBar().showMessage('Auto calculations done.')

    def zoom_to_uni(self, row):
        self.canvas.toolbar.push_current()
        T, p = self.get_trimmed_uni(row)
        dT = max((T.max() - T.min()) / 10, 0.01)
        dp = max((p.max() - p.min()) / 10, 0.001)
        self.ax.set_xlim([T.min() - dT, T.max() + dT])
        self.ax.set_ylim([p.min() - dp, p.max() + dp])
        self.canvas.toolbar.push_current()
        self.canvas.draw()

    def remove_inv(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            invnum = self.invmodel.data(idx[0])
            todel = True
            # Check ability to delete
            for row in self.unimodel.unilist:
                if row[2] == invnum or row[3] == invnum:
                    if row[4]['manual']:
                        todel = False
            if todel:
                msg = '{}\nAre you sure?'.format(self.invmodel.data(idx[1]))
                qb = QtWidgets.QMessageBox
                reply = qb.question(self, 'Remove invariant point',
                                    msg, qb.Yes, qb.No)
                if reply == qb.Yes:

                    # Check unilines begins and ends
                    for row in self.unimodel.unilist:
                        if row[2] == invnum:
                            row[2] = 0
                        if row[3] == invnum:
                            row[3] = 0
                    self.invmodel.removeRow(idx[0])
                    self.changed = True
                    self.plot()
                    self.statusBar().showMessage('Invariant point removed')
            else:
                self.statusBar().showMessage('Cannot delete invariant point, which define user-defined univariant line.')

    def remove_uni(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            msg = '{}\nAre you sure?'.format(self.unimodel.data(idx[1]))
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Remove univariant line',
                                msg, qb.Yes, qb.No)
            if reply == qb.Yes:
                self.unimodel.removeRow(idx[0])
                self.changed = True
                self.plot()
                self.statusBar().showMessage('Univariant line removed')

    def clicker(self, event):
        self.cid.onmove(event)
        if event.inaxes is not None:
            self.cid.clear(event)
            phases, out = self.get_phases_out()
            r = dict(phases=phases, out=out, cmd='', variance=-1, manual=True)
            label = self.format_label(phases, out)
            isnew, id = self.getidinv(r)
            addinv = AddInv(label, parent=self)
            addinv.set_from_event(event)
            respond = addinv.exec()
            if respond == QtWidgets.QDialog.Accepted:
                T, p = addinv.getValues()
                r['T'], r['p'], r['output'] = np.array([T]), np.array([p]), 'User-defined invariant point.'
                if isnew:
                    self.invmodel.appendRow((id, label, r))
                    if self.checkAutoconnectInv.isChecked():
                        for unirow in self.unimodel.unilist:
                            if inv_on_uni(unirow[4]['phases'], unirow[4]['out'], phases, out):
                                candidates = [id]
                                for invrow in self.invmodel.invlist[1:-1]:
                                    if inv_on_uni(unirow[4]['phases'], unirow[4]['out'], invrow[2]['phases'], invrow[2]['out']):
                                        candidates.append(invrow[0])
                                if len(candidates) == 2:
                                    self.uniview.selectRow(self.unimodel.lookup[unirow[0]])
                                    self.auto_connect(unirow, candidates, self.unisel.selectedIndexes())
                else:
                    row = self.invmodel.getRowFromId(id)
                    row[2] = r
                    # retrim affected
                    for row in self.unimodel.unilist:
                        if row[2] == id or row[3] == id:
                            self.trimuni(row)
                self.invview.resizeColumnsToContents()
                self.plot()
                idx = self.invmodel.index(self.invmodel.lookup[id], 0, QtCore.QModelIndex())
                self.show_inv(idx)
                self.statusBar().showMessage('User-defined invariant point added.')
            self.pushManual.setChecked(False)

    def add_userdefined(self, checked=True):
        if self.ready:
            phases, out = self.get_phases_out()
            if len(out) == 1:
                if checked:
                    label = self.format_label(phases, out)
                    invs = []
                    for row in self.invmodel.invlist[1:]:
                        d = row[2]
                        if self.checkStrict.isChecked() or self.checkAutoconnectUni.isChecked():
                            filtered = inv_on_uni(phases, out, row[2]['phases'], row[2]['out'])
                        else:
                            filtered = phases.issubset(row[2]['phases']) and out.issubset(row[2]['out'])
                        #if phases.issubset(d['phases']) and out.issubset(d['out']):
                        if filtered:
                           invs.append(row[0])
                    r = dict(phases=phases, out=out, cmd='', variance=-1,
                             p=np.array([]), T=np.array([]), manual=True,
                             output='User-defined univariant line.')
                    isnew, id = self.getiduni(r)
                    if self.checkAutoconnectUni.isChecked():
                        if len(invs) == 2:
                            b, e = invs
                            if isnew:
                                self.unimodel.appendRow((id, label, b, e, r))
                            else:
                                row = self.unimodel.getRowFromId(id)
                                row[2] = b
                                row[3] = e
                                row[4] = r
                                if label:
                                    row[1] = label
                            row = self.unimodel.getRowFromId(id)
                            self.trimuni(row)
                            # if self.unihigh is not None:
                            #     self.clean_high()
                            #     self.unihigh.set_data(row[4]['fT'], row[4]['fp'])
                            self.uniview.resizeColumnsToContents()
                            self.changed = True
                            self.plot()
                            idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                            if isnew:
                                self.uniview.selectRow(idx.row())
                                self.uniview.scrollToBottom()
                                self.statusBar().showMessage('User-defined univariant line added.')
                            else:
                                self.statusBar().showMessage('Existing univariant line changed to user-defined one.')
                            self.show_uni(idx)
                        else:
                            self.statusBar().showMessage('Not enough invariant points calculated for selected univariant line.')
                    else:
                        if self.checkStrict.isChecked():
                            okadd = len(invs) == 2
                        else:
                            okadd = len(invs) > 1
                        if okadd:
                            if not isnew:
                                ra = self.unimodel.getRowFromId(id)
                                adduni = AddUni(label, invs, selected=(ra[2], ra[3]), parent=self)
                            else:
                                adduni = AddUni(label, invs, selected=(invs[0], invs[1]), parent=self)
                            respond = adduni.exec()
                            if respond == QtWidgets.QDialog.Accepted:
                                b, e = adduni.getValues()
                                if b != e:
                                    if isnew:
                                        self.unimodel.appendRow((id, label, b, e, r))
                                    else:
                                        row = self.unimodel.getRowFromId(id)
                                        row[2] = b
                                        row[3] = e
                                        row[4] = r
                                        if label:
                                            row[1] = label
                                    row = self.unimodel.getRowFromId(id)
                                    self.trimuni(row)
                                    # if self.unihigh is not None:
                                    #     self.clean_high()
                                    #     self.unihigh.set_data(row[4]['fT'], row[4]['fp'])
                                    self.uniview.resizeColumnsToContents()
                                    self.changed = True
                                    self.plot()
                                    idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                                    if isnew:
                                        self.uniview.selectRow(idx.row())
                                        self.uniview.scrollToBottom()
                                        self.statusBar().showMessage('User-defined univariant line added.')
                                    else:
                                        self.statusBar().showMessage('Existing univariant line changed to user-defined one.')
                                    self.show_uni(idx)
                                else:
                                    msg = 'Begin and end must be different.'
                                    qb = QtWidgets.QMessageBox
                                    qb.critical(self, 'Error!', msg, qb.Abort)
                        else:
                            self.statusBar().showMessage('Not enough invariant points calculated for selected univariant line.')
                    self.pushManual.setChecked(False)
            elif len(out) == 2:
                if checked:
                    # cancle zoom and pan action on toolbar
                    if self.toolbar._active == "PAN":
                        self.toolbar.pan()
                    elif self.toolbar._active == "ZOOM":
                        self.toolbar.zoom()
                    self.cid = Cursor(self.ax, useblit=False, color='red', linewidth=1)
                    self.cid.connect_event('button_press_event', self.clicker)
                    self.tabMain.setCurrentIndex(0)
                    self.statusBar().showMessage('Click on canvas to add invariant point.')
                    self.pushDogmin.toggled.disconnect()
                    self.pushDogmin.setCheckable(False)
                else:
                    self.canvas.mpl_disconnect(self.cid)
                    self.statusBar().showMessage('')
                    self.pushDogmin.toggled.connect(self.do_dogmin)
                    self.pushDogmin.setCheckable(True)
                    self.cid.disconnect_events()
                    self.cid = None
            else:
                self.statusBar().showMessage('Select exactly one out phase for univariant line or two phases for invariant point.')
                self.pushManual.setChecked(False)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
            self.pushManual.setChecked(False)

    def dogminer(self, event):
        self.cid.onmove(event)
        if event.inaxes is not None:
            self.cid.clear(event)
            phases, out = self.get_phases_out()
            which = phases.difference(self.prj.excess)
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (trange[0] - ts, trange[1] + ts)
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (prange[0] - ps, prange[1] + ps)
            steps = self.spinSteps.value()
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            prec = max(int(2 - np.floor(np.log10(min(np.diff(trange)[0], np.diff(prange)[0])))), 0)
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            self.prj.update_scriptfile(dogmin='yes {}'.format(doglevel), which=which,
                                       T='{:.{prec}f}'.format(event.xdata, prec=prec),
                                       p='{:.{prec}f}'.format(event.ydata, prec=prec))
            #self.read_scriptfile()
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.prj.tc_dogmin(variance)
            res, resic = self.prj.parse_dogmin()
            if res is not None:
                self.textOutput.setPlainText(res)
                self.textFullOutput.setPlainText(resic)
                self.logDogmin.setPlainText(res + resic)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.prj.workdir) + tcout)
                self.statusBar().showMessage('Dogmin finished.')
            else:
                self.statusBar().showMessage('Dogmin failed.')
            self.pushDogmin.setChecked(False)

    def do_dogmin(self, checked=True):
        if self.ready:
            if checked:
                # cancle zoom and pan action on toolbar
                if self.toolbar._active == "PAN":
                    self.toolbar.pan()
                elif self.toolbar._active == "ZOOM":
                    self.toolbar.zoom()
                self.cid = Cursor(self.ax, useblit=False, color='red', linewidth=1)
                self.cid.connect_event('button_press_event', self.dogminer)
                self.tabMain.setCurrentIndex(0)
                self.statusBar().showMessage('Click on canvas to run dogmin at this point.')
                self.pushManual.toggled.disconnect()
                self.pushManual.setCheckable(False)
            else:
                self.prj.update_scriptfile(dogmin='no')
                self.read_scriptfile()
                QtWidgets.QApplication.restoreOverrideCursor()
                self.statusBar().showMessage('')
                self.pushManual.toggled.connect(self.add_userdefined)
                self.pushManual.setCheckable(True)
                self.cid.disconnect_events()
                self.cid = None
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
            self.pushDogmin.setChecked(False)

    def dogmin_select_phases(self):
        if self.ready:
            dgtxt = self.logDogmin.toPlainText()
            try:
                phases = set(dgtxt.split('phases: ')[1].split(' (')[0].split())
                r = dict(phases=phases, out=set(), output='User-defined')
                self.set_phaselist(r, show_output=False)
            except:
                self.statusBar().showMessage('You need to run dogmin first.')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def dogmin_set_guesses(self):
        if self.ready:
            dgtxt = self.logDogmin.toPlainText()
            try:
                block = [ln for ln in dgtxt.splitlines() if ln != '']
                xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 1
                gixe = xyz[-1] + 2
                ptguess = block[gixs:gixe]
                self.prj.update_scriptfile(guesses=ptguess)
                self.read_scriptfile()
                self.statusBar().showMessage('Dogmin ptuess set.')
            except:
                self.statusBar().showMessage('You need to run dogmin first.')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def read_scriptfile(self):
        if self.ready:
            with self.prj.scriptfile.open('r', encoding=self.prj.TCenc) as f:
                self.outScript.setPlainText(f.read())
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def save_scriptfile(self):
        if self.ready:
            with self.prj.scriptfile.open('w', encoding=self.prj.TCenc) as f:
                f.write(self.outScript.toPlainText())
            self.reinitialize()
            self.apply_setting(1)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def closeEvent(self, event):
        """Catch exit of app.
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Cancel | qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
                if self.project is not None:
                    self.app_settings(write=True)
                    event.accept()
                else:
                    event.ignore()
            elif reply == qb.Discard:
                event.accept()
            else:
                event.ignore()

    def check_validity(self, *args, **kwargs):
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QtGui.QValidator.Acceptable:
            color = '#c4df9b'  # green
        elif state == QtGui.QValidator.Intermediate:
            color = '#fff79a'  # yellow
        else:
            color = '#f6989d'  # red
        sender.setStyleSheet('QLineEdit { background-color: %s }' % color)

    def apply_setting(self, bitopt=0):
        """Apply settings
        0 bit from text to app and plot (1)
        1 bit from axes to text         (2)
        2 bit from app to text          (4)
        3 bit from default to text      (8)
        """
        # app settings
        if (1 << 0) & bitopt:
            self.app_settings(write=True)
        if (1 << 2) & bitopt:
            self.app_settings()
        # proj settings
        if self.ready:
            fmt = lambda x: '{:.{prec}f}'.format(x, prec=self.spinPrec.value())
            if (1 << 0) & bitopt:
                self.prj.trange = (float(self.tminEdit.text()),
                                   float(self.tmaxEdit.text()))
                self.prj.prange = (float(self.pminEdit.text()),
                                   float(self.pmaxEdit.text()))
                self.ax.set_xlim(self.prj.trange)
                self.ax.set_ylim(self.prj.prange)
                # clear navigation toolbar history
                self.toolbar.update()
                self.statusBar().showMessage('Settings applied.')
                self.changed = True
                self.figure.clear()
                self.plot()
            if (1 << 1) & bitopt:
                self.tminEdit.setText(fmt(self.ax.get_xlim()[0]))
                self.tmaxEdit.setText(fmt(self.ax.get_xlim()[1]))
                self.pminEdit.setText(fmt(self.ax.get_ylim()[0]))
                self.pmaxEdit.setText(fmt(self.ax.get_ylim()[1]))
            if (1 << 2) & bitopt:
                self.tminEdit.setText(fmt(self.prj.trange[0]))
                self.tmaxEdit.setText(fmt(self.prj.trange[1]))
                self.pminEdit.setText(fmt(self.prj.prange[0]))
                self.pmaxEdit.setText(fmt(self.prj.prange[1]))
            if (1 << 3) & bitopt:
                self.tminEdit.setText(fmt(self.prj.deftrange[0]))
                self.tmaxEdit.setText(fmt(self.prj.deftrange[1]))
                self.pminEdit.setText(fmt(self.prj.defprange[0]))
                self.pmaxEdit.setText(fmt(self.prj.defprange[1]))
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def phase_changed(self, item):
        """Manage phases in outmodel based on selection in phase model.
        """
        if item.checkState():
            outitem = item.clone()
            outitem.setCheckState(QtCore.Qt.Unchecked)
            self.outmodel.appendRow(outitem)
            self.outmodel.sort(0, QtCore.Qt.AscendingOrder)
        else:
            for it in self.outmodel.findItems(item.text()):
                self.outmodel.removeRow(it.row())

    def format_label(self, phases, out):
        return (' '.join(sorted(list(phases.difference(self.prj.excess)))) +
                ' - ' +
                ' '.join(sorted(list(out))))

    def do_calc(self, cT, phases={}, out={}):
        if self.ready:
            if phases == {} and out == {}:
                phases, out = self.get_phases_out()
            self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, 0), trange[1] + ts)
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, 0), prange[1] + ps)
            steps = self.spinSteps.value()

            if len(out) == 1:
                rt = dict(phases=phases, out=out, output='User-defined')
                isnew, id = self.getiduni(rt)
                if cT:
                    tcout, ans = self.prj.tc_calc_t(rt['phases'], rt['out'], prange = prange, trange=trange, steps=steps)
                else:
                    tcout, ans = self.prj.tc_calc_p(rt['phases'], rt['out'], prange = prange, trange=trange, steps=steps)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.prj.workdir) + tcout)
                status, variance, pts, res, output = self.prj.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    r = dict(phases=rt['phases'], out=rt['out'], cmd=ans, variance=variance,
                             p=pts[0], T=pts[1], manual=False,
                             output=output, results=res)
                    label = self.format_label(r['phases'], r['out'])
                    if isnew:
                        self.unimodel.appendRow((id, label, 0, 0, r))
                        row = self.unimodel.getRowFromId(id)
                        self.trimuni(row)
                        self.uniview.resizeColumnsToContents()
                        self.changed = True
                        # self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
                        idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                        self.uniview.selectRow(idx.row())
                        self.uniview.scrollToBottom()
                        if self.checkAutoconnectUni.isChecked():
                            candidates = []
                            for invrow in self.invmodel.invlist[1:]:
                                if inv_on_uni(phases, out, invrow[2]['phases'], invrow[2]['out']):
                                    candidates.append(invrow[0])
                            if len(candidates) == 2:
                                self.auto_connect(row, candidates, self.unisel.selectedIndexes())
                        self.plot()
                        self.show_uni(idx)
                        self.statusBar().showMessage('New univariant line calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            row = self.unimodel.getRowFromId(id)
                            row[1] = label
                            row[4] = r
                            self.trimuni(row)
                            self.changed = True
                            self.uniview.resizeColumnsToContents()
                            idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                            self.uniview.selectRow(idx.row())
                            self.unimodel.dataChanged.emit(idx, idx)
                            self.plot()
                            self.show_uni(idx)
                            self.statusBar().showMessage('Univariant line {} re-calculated.'.format(id))
                        else:
                            self.statusBar().showMessage('Univariant line already exists.')
            elif len(out) == 2:
                rt = dict(phases=phases, out=out, output='User-defined')
                isnew, id = self.getidinv(rt)
                tcout, ans = self.prj.tc_calc_pt(rt['phases'], rt['out'], prange = prange, trange=trange)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.prj.workdir) + tcout)
                status, variance, pts, res, output = self.prj.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                else:
                    r = dict(phases=rt['phases'], out=rt['out'], cmd=ans, variance=variance,
                             p=pts[0], T=pts[1], manual=False,
                             output=output, results=res)
                    label = self.format_label(r['phases'], r['out'])
                    if isnew:
                        self.invmodel.appendRow((id, label, r))
                        self.invview.resizeColumnsToContents()
                        self.changed = True
                        idx = self.invmodel.index(self.invmodel.lookup[id], 0, QtCore.QModelIndex())
                        self.invview.selectRow(idx.row())
                        self.invview.scrollToBottom()
                        if self.checkAutoconnectInv.isChecked():
                            for unirow in self.unimodel.unilist:
                                if inv_on_uni(unirow[4]['phases'], unirow[4]['out'], phases, out):
                                    candidates = [id]
                                    for invrow in self.invmodel.invlist[1:-1]:
                                        if inv_on_uni(unirow[4]['phases'], unirow[4]['out'], invrow[2]['phases'], invrow[2]['out']):
                                            candidates.append(invrow[0])
                                    if len(candidates) == 2:
                                        self.uniview.selectRow(self.unimodel.lookup[unirow[0]])
                                        self.auto_connect(unirow, candidates, self.unisel.selectedIndexes())
                        self.plot()
                        self.show_inv(idx)
                        self.statusBar().showMessage('New invariant point calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            row = self.invmodel.getRowFromId(id)
                            row[1] = label
                            row[2] = r
                            # retrim affected
                            for row in self.unimodel.unilist:
                                if row[2] == id or row[3] == id:
                                    self.trimuni(row)
                            self.changed = True
                            idx = self.invmodel.index(self.invmodel.lookup[id], 0, QtCore.QModelIndex())
                            self.invview.selectRow(idx.row())
                            self.show_inv(idx)
                            self.plot()
                            self.invmodel.dataChanged.emit(idx, idx)
                            self.statusBar().showMessage('Invariant point {} re-calculated.'.format(id))
                        else:
                            self.statusBar().showMessage('Invariant point already exists.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out)))
            #########
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def getiduni(self, zm=None):
        '''Return id of either new or existing univariant line'''
        ids = 0
        # collect polymorphs identities
        if zm is not None:
            outs = [zm['out']]
            for poly in polymorphs:
                if poly.issubset(zm['phases']):
                    outs.append(poly.difference(zm['out']))

        for r in self.unimodel.unilist:
            if zm is not None:
                if r[4]['phases'] == zm['phases']:
                    if r[4]['out'] in outs:
                        zm['out'] = r[4]['out'] # switch to already used ??? Needed ???
                        return False, r[0]
            ids = max(ids, r[0])
        return True, ids + 1

    def getidinv(self, zm=None):
        '''Return id of either new or existing invvariant point'''
        ids = 0
        # collect polymorphs identities
        if zm is not None:
            outs = [zm['out']]
            for poly in polymorphs:
                if poly.issubset(zm['phases']):
                    outs.append(zm['out'].difference(poly).union(poly.difference(zm['out'])))

        for r in self.invmodel.invlist[1:]:
            if zm is not None:
                if r[2]['phases'] == zm['phases']:
                    if r[2]['out'] in outs:
                        zm['out'] = r[2]['out'] # switch to already used ??? Needed ???
                        return False, r[0]
            ids = max(ids, r[0])
        return True, ids + 1

    def trimuni(self, row):
        if not row[4]['manual']:
            ratio = (self.prj.trange[1] - self.prj.trange[0]) / (self.prj.prange[1] - self.prj.prange[0])
            xy = np.array([row[4]['T'], ratio * row[4]['p']]).T
            line = LineString(xy)
            if row[2] > 0:
                dt = self.invmodel.getDataFromId(row[2])
                p1 = Point(dt['T'][0], ratio * dt['p'][0])
            else:
                p1 = Point(row[4]['T'][0], ratio * row[4]['p'][0])
            if row[3] > 0:
                dt = self.invmodel.getDataFromId(row[3])
                p2 = Point(dt['T'][0], ratio * dt['p'][0])
            else:
                p2 = Point(row[4]['T'][-1], ratio * row[4]['p'][-1])
            # vertex distances
            vdst = np.array([line.project(Point(*v)) for v in xy])
            d1 = line.project(p1)
            d2 = line.project(p2)
            if d1 > d2:
                d1, d2 = d2, d1
                row[2], row[3] = row[3], row[2]
            # get indexex of points to keep
            row[4]['begix'] = np.flatnonzero(vdst >= d1)[0]
            row[4]['endix'] = np.flatnonzero(vdst <= d2)[-1]

    def get_trimmed_uni(self, row):
        if row[2] > 0:
            dt = self.invmodel.getDataFromId(row[2])
            T1, p1 = dt['T'][0], dt['p'][0]
        else:
            T1, p1 = [], []
        if row[3] > 0:
            dt = self.invmodel.getDataFromId(row[3])
            T2, p2 = dt['T'][0], dt['p'][0]
        else:
            T2, p2 = [], []
        if not row[4]['manual']:
            T = row[4]['T'][row[4]['begix']:row[4]['endix'] + 1]
            p = row[4]['p'][row[4]['begix']:row[4]['endix'] + 1]
        else:
            if row[2] == 0 and row[3] == 0:
                T, p = row[4]['T'], row[4]['p']
            else:
                T, p = [], []
        return np.hstack((T1, T, T2)), np.hstack((p1, p, p2))

    def getunilabelpoint(self, T, p):
        if len(T) > 1:
            dT = np.diff(T)
            dp = np.diff(p)
            d = np.sqrt(dT**2 + dp**2)
            if np.sum(d) > 0:
                cl = np.append([0], np.cumsum(d))
                ix = np.interp(np.sum(d) / 2, cl, range(len(cl)))
                cix = int(ix)
                return T[cix] + (ix - cix) * dT[cix], p[cix] + (ix - cix) * dp[cix]
            else:
                return T[0], p[0]
        else:
            return T[0], p[0]

    def plot(self):
        if self.ready:
            lalfa = self.spinAlpha.value() / 100
            fsize = self.spinFontsize.value()
            unilabel_kw = dict(ha='center', va='center', size=fsize,
                               bbox=dict(boxstyle="round,pad=0.2", fc='cyan', alpha=lalfa, pad=2))
            invlabel_kw = dict(ha='center', va='center', size=fsize,
                               bbox=dict(boxstyle="round,pad=0.2", fc='yellow', alpha=lalfa, pad=2))
            axs = self.figure.get_axes()
            if axs:
                self.ax = axs[0]
                cur = (self.ax.get_xlim(), self.ax.get_ylim())
            else:
                cur = None
                self.ax = self.figure.add_subplot(111)
            self.ax.cla()
            self.ax.format_coord = self.format_coord
            for k in self.unimodel.unilist:
                T, p = self.get_trimmed_uni(k)
                self.ax.plot(T, p, 'k')
                if self.checkLabelUni.isChecked():
                    Tl, pl = self.getunilabelpoint(T, p)
                    if self.checkLabelUniText.isChecked():
                        self.ax.annotate(s='{} {}'.format(str(k[0]), ' '.join(k[4]['out'])), xy=(Tl, pl), **unilabel_kw)
                    else:
                        self.ax.annotate(s=str(k[0]), xy=(Tl, pl), **unilabel_kw)
                        #self.ax.text(Tl, pl, str(k[0]), **unilabel_kw)
            for k in self.invmodel.invlist[1:]:
                T, p = k[2]['T'][0], k[2]['p'][0]
                if self.checkLabelInv.isChecked():
                    if self.checkLabelInvText.isChecked():
                        self.ax.annotate(s='{} {}'.format(str(k[0]), ' '.join(k[2]['out'])), xy=(T, p), **invlabel_kw)
                    else:
                        self.ax.annotate(s=str(k[0]), xy=(T, p), **invlabel_kw)
                        #self.ax.text(T, p, str(k[0]), **invlabel_kw)
                else:
                    if self.checkDotInv.isChecked():
                        self.ax.plot(T, p, 'k.')
            self.ax.set_xlabel('Temperature [C]')
            self.ax.set_ylabel('Pressure [kbar]')
            ex = list(self.prj.excess)
            ex.insert(0, '')
            self.ax.set_title(self.prj.axname + ' +'.join(ex))
            if cur is None:
                self.ax.set_xlim(self.prj.trange)
                self.ax.set_ylim(self.prj.prange)
            else:
                self.ax.set_xlim(cur[0])
                self.ax.set_ylim(cur[1])
            if self.unihigh is not None and self.unisel.hasSelection():
                idx = self.unisel.selectedIndexes()
                row = self.unimodel.getRow(idx[0])
                T, p = self.get_trimmed_uni(row)
                self.unihigh = self.ax.plot(T, p, '-', **unihigh_kw)
            if self.invhigh is not None and self.invsel.hasSelection():
                idx = self.invsel.selectedIndexes()
                dt = self.invmodel.getData(idx[0], 'Data')
                self.invhigh = self.ax.plot(dt['T'], dt['p'], 'o', **invhigh_kw)
            self.canvas.draw()

    def check_prj_areas(self):
        if self.ready:
            if not hasattr(self.ax, 'areas_shown'):
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                ps = PTPS(PSB(self.data))
                if ps.shapes:
                    vari = [ps.variance[k] for k in ps]
                    poc = max(vari) - min(vari) + 1
                    pscolors = cm.get_cmap('cool')(np.linspace(0, 1, poc))
                    # Set alpha
                    pscolors[:, -1] = 0.6 # alpha
                    pscmap = ListedColormap(pscolors)
                    norm = BoundaryNorm(np.arange(min(vari) - 0.5, max(vari) + 1.5), poc, clip=True)
                    for k in ps:
                        self.ax.add_patch(PolygonPatch(ps.shapes[k], fc=pscmap(norm(ps.variance[k])), ec='none'))
                    self.ax.areas_shown = True
                    self.canvas.draw()
                else:
                    self.statusBar().showMessage('No areas created.')
                QtWidgets.QApplication.restoreOverrideCursor()
            else:
                self.figure.clear()
                self.plot()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def show_topology(self):
        if self.ready:
            if NX_OK:
                dia = TopologyGraph(PSB(self.data))
                dia.show()
            else:
                self.statusBar().showMessage('Topology graph needs networkx to be installed')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')


class InvModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(InvModel, self).__init__(parent, *args)
        self.invlist = []
        self.header = ['ID', 'Label', 'Data']
        self.lookup = {}

    def rowCount(self, parent=None):
        return len(self.invlist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        # elif role == QtCore.Qt.ForegroundRole:
        #     if self.invlist[index.row()][self.header.index('Data')]['manual']:
        #         brush = QtGui.QBrush()
        #         brush.setColor(QtGui.QColor('red'))
        #         return brush
        elif role == QtCore.Qt.FontRole:
            if self.invlist[index.row()][self.header.index('Data')]['manual']:
                font = QtGui.QFont()
                font.setBold(True)
                return font
        elif role != QtCore.Qt.DisplayRole:
            return None
        else:
            return self.invlist[index.row()][index.column()]

    def appendRow(self, datarow):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.invlist), len(self.invlist))
        self.invlist.append(list(datarow))
        self.endInsertRows()
        self.lookup[datarow[0]] = self.rowCount() - 1

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        del self.invlist[index.row()]
        self.endRemoveRows()
        self.lookup = {dt[0]: ix + 1 for ix, dt in enumerate(self.invlist[1:])}

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def getData(self, index, what='Data'):
        return self.invlist[index.row()][self.header.index(what)]

    def getRow(self, index):
        return self.invlist[index.row()]

    def getDataFromId(self, id, what='Data'):
        # print(id, self.rowCount(), what, self.lookup)
        return self.invlist[self.lookup[id]][self.header.index(what)]

    def getRowFromId(self, id):
        return self.invlist[self.lookup[id]]


class UniModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(UniModel, self).__init__(parent, *args)
        self.unilist = []
        self.header = ['ID', 'Label', 'Begin', 'End', 'Data']
        self.lookup = {}

    def rowCount(self, parent=None):
        return len(self.unilist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        # elif role == QtCore.Qt.ForegroundRole:
        #     if self.unilist[index.row()][self.header.index('Data')]['manual']:
        #         brush = QtGui.QBrush()
        #         brush.setColor(QtGui.QColor('red'))
        #         return brush
        elif role == QtCore.Qt.FontRole:
            if self.unilist[index.row()][self.header.index('Data')]['manual']:
                font = QtGui.QFont()
                font.setBold(True)
                return font
        elif role != QtCore.Qt.DisplayRole:
            return None
        else:
            return self.unilist[index.row()][index.column()]

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        # DO change and emit plot
        if role == QtCore.Qt.EditRole:
            self.unilist[index.row()][index.column()] = value
            self.dataChanged.emit(index, index)
        return False

    def appendRow(self, datarow):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.unilist), len(self.unilist))
        self.unilist.append(list(datarow))
        self.endInsertRows()
        self.lookup[datarow[0]] = self.rowCount() - 1

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        del self.unilist[index.row()]
        self.endRemoveRows()
        self.lookup = {dt[0]: ix for ix, dt in enumerate(self.unilist)}

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def flags(self, index):
        if index.column() > 1:
            return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def getData(self, index, what='Data'):
        return self.unilist[index.row()][self.header.index(what)]

    def getRow(self, index):
        return self.unilist[index.row()]

    def getDataFromId(self, id, what='Data'):
        return self.unilist[self.lookup[id]][self.header.index(what)]

    def getRowFromId(self, id):
        return self.unilist[self.lookup[id]]


class ComboDelegate(QtWidgets.QItemDelegate):
    """
    A delegate that places a fully functioning QtWidgets.QComboBox in every
    cell of the column to which it's applied
    """
    def __init__(self, parent, invmodel, strict):
        super(ComboDelegate, self).__init__(parent)
        self.invmodel = invmodel
        self.strict = strict

    def createEditor(self, parent, option, index):
        #r = index.model().getData(index, 'Data')
        r = index.model().getRow(index)
        if index.column() == 2:
            other = r[3]
        else:
            other = r[2]
        #phases, out = r[4]['phases'], r[4]['out']
        combomodel = QtGui.QStandardItemModel()
        if not r[4]['manual']:
            item = QtGui.QStandardItem('0')
            item.setData(0, 1)
            combomodel.appendRow(item)
        # filter possible candidates
        for row in self.invmodel.invlist[1:]:
            if self.strict.isChecked():
                filtered = inv_on_uni(r[4]['phases'], r[4]['out'], row[2]['phases'], row[2]['out'])
            else:
                filtered = r[4]['phases'].issubset(row[2]['phases']) and r[4]['out'].issubset(row[2]['out'])
            #if phases.issubset(d['phases']) and out.issubset(d['out']):
            if row[0] != other and filtered:
                item = QtGui.QStandardItem(str(row[0]))
                item.setData(row[0], 1)
                combomodel.appendRow(item)
        combo = QtWidgets.QComboBox(parent)
        combo.setModel(combomodel)
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentText(str(index.model().data(index)))
        # auto open combobox
        #editor.showPopup()

    def setModelData(self, editor, model, index):
        if index.column() == 2:
            other = model.getData(index, 'End')
        else:
            other = model.getData(index, 'Begin')
        new = editor.currentData(1)
        if other == new and new != 0:
            editor.setCurrentText(str(model.data(index)))
            self.parent().statusBar().showMessage('Begin and end must be different.')
        else:
            model.setData(index, new)


class AddInv(QtWidgets.QDialog, Ui_AddInv):
    """Add inv dialog class
    """
    def __init__(self, label, parent=None):
        super(AddInv, self).__init__(parent)
        self.setupUi(self)
        self.labelEdit.setText(label)
        # validator
        validator = QtGui.QDoubleValidator()
        validator.setLocale(QtCore.QLocale.c())
        self.tEdit.setValidator(validator)
        self.tEdit.textChanged.connect(self.check_validity)
        self.tEdit.textChanged.emit(self.tEdit.text())
        self.pEdit.setValidator(validator)
        self.pEdit.textChanged.connect(self.check_validity)
        self.pEdit.textChanged.emit(self.pEdit.text())

    def check_validity(self, *args, **kwargs):
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QtGui.QValidator.Acceptable:
            color = '#c4df9b'  # green
        elif state == QtGui.QValidator.Intermediate:
            color = '#fff79a'  # yellow
        else:
            color = '#f6989d'  # red
        sender.setStyleSheet('QLineEdit { background-color: %s }' % color)

    def set_from_event(self, event):
        self.tEdit.setText(str(event.xdata))
        self.pEdit.setText(str(event.ydata))

    def getValues(self):
        T = float(self.tEdit.text())
        p = float(self.pEdit.text())
        return T, p


class AddUni(QtWidgets.QDialog, Ui_AddUni):
    """Add uni dialog class
    """
    def __init__(self, label, items, selected=None, parent=None):
        super(AddUni, self).__init__(parent)
        self.setupUi(self)
        self.labelEdit.setText(label)
        self.combomodel = QtGui.QStandardItemModel()
        for item in items:
            it = QtGui.QStandardItem(str(item))
            it.setData(item, 1)
            self.combomodel.appendRow(it)
        self.comboBegin.setModel(self.combomodel)
        self.comboEnd.setModel(self.combomodel)
        if selected:
            if selected[0] in items:
                self.comboBegin.setCurrentIndex(items.index(selected[0]))
            if selected[1] in items:
                self.comboEnd.setCurrentIndex(items.index(selected[1]))

    def getValues(self):
        b = self.comboBegin.currentData(1)
        e = self.comboEnd.currentData(1)
        return b, e


class UniGuess(QtWidgets.QDialog, Ui_UniGuess):
    """Choose uni pt dialog class
    """
    def __init__(self, values, parent=None):
        super(UniGuess, self).__init__(parent)
        self.setupUi(self)
        self.comboPoint.addItems(values)

    def getValue(self):
        return self.comboPoint.currentIndex()


class AboutDialog(QtWidgets.QDialog):
    """About dialog
    """
    def __init__(self, version, parent=None):
        """Display a dialog that shows application information."""
        super(AboutDialog, self).__init__(parent)

        self.setWindowTitle('About')
        self.resize(300, 100)

        about = QtWidgets.QLabel('PSbuilder {}\nTHERMOCALC front-end for constructing PT pseudosections'.format(version))
        about.setAlignment(QtCore.Qt.AlignCenter)

        author = QtWidgets.QLabel('Ondrej Lexa')
        author.setAlignment(QtCore.Qt.AlignCenter)

        github = QtWidgets.QLabel('GitHub: ondrolexa')
        github.setAlignment(QtCore.Qt.AlignCenter)

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignVCenter)

        self.layout.addWidget(about)
        self.layout.addWidget(author)
        self.layout.addWidget(github)

        self.setLayout(self.layout)


class OutputDialog(QtWidgets.QDialog):
    """Output dialog
    """
    def __init__(self, title, txt, parent=None):
        """Display a dialog that shows application information."""
        super(OutputDialog, self).__init__(parent)

        self.setWindowTitle(title)
        self.resize(800, 600)

        self.plainText = QtWidgets.QPlainTextEdit(self)
        self.plainText.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.plainText.setReadOnly(True)
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.plainText.setFont(f)
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignVCenter)
        self.layout.addWidget(self.plainText)
        self.setLayout(self.layout)
        self.plainText.setPlainText(txt)


class TopologyGraph(QtWidgets.QDialog):
    def __init__(self, psb, parent=None):
        super(TopologyGraph, self).__init__(parent)
        self.setWindowTitle('Topology graph')
        window_icon = resource_filename('pypsbuilder', 'images/pypsbuilder.png')
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.setWindowFlags(QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.canvas)
        layout.addWidget(self.toolbar)
        self.setLayout(layout)

        import networkx as nx

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        G = nx.Graph()
        pos = {}
        labels = {}
        for inv in psb.invlist:
            G.add_node(inv[0])
            pos[inv[0]] = inv[2]['p'][0], inv[2]['T'][0]
            labels[inv[0]] = str(inv[0])

        edges = {}
        for uni in psb.unilist:
            if uni[2] != 0 and uni[3] != 0:
                out = frozenset(uni[4]['out'])
                G.add_edge(uni[2], uni[3], out=list(out)[0])
                if out in edges:
                    edges[out].append((uni[2], uni[3]))
                else:
                    edges[out] = [(uni[2], uni[3])]

        #npos = nx.kamada_kawai_layout(G, pos=nx.planar_layout(G))
        npos = nx.kamada_kawai_layout(G, pos=pos)
        widths = Normalize(vmin=0, vmax=len(edges))
        color = cm.get_cmap('tab20', len(edges))
        for ix, out in enumerate(edges):
            nx.draw_networkx_edges(G, npos, ax=ax, edgelist=edges[out],
                                   width=2 + 6*widths(ix), alpha=0.5, edge_color=len(edges[out]) * [color(ix)], label=list(out)[0])

        nx.draw_networkx_nodes(G, npos, ax=ax, node_color='k')
        nx.draw_networkx_labels(G, npos, labels, ax=ax, font_size=12, font_weight='bold', font_color='w')

        # Shrink current axis by 20%
        self.figure.tight_layout()
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.85, box.height])

        # Put a legend to the right of the current axis
        ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        # refresh canvas
        self.canvas.draw()


def main():
    application = QtWidgets.QApplication(sys.argv)
    window = PSBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) / 2
    height = (desktop.height() - window.height()) / 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())


if __name__ == "__main__":
    main()
