# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'addinv.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_AddInv(object):
    def setupUi(self, AddInv):
        AddInv.setObjectName("AddInv")
        AddInv.resize(300, 104)
        self.verticalLayout = QtWidgets.QVBoxLayout(AddInv)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label = QtWidgets.QLabel(AddInv)
        self.label.setObjectName("label")
        self.horizontalLayout_2.addWidget(self.label)
        self.labelEdit = QtWidgets.QLineEdit(AddInv)
        self.labelEdit.setReadOnly(True)
        self.labelEdit.setObjectName("labelEdit")
        self.horizontalLayout_2.addWidget(self.labelEdit)
        self.checkKeep = QtWidgets.QCheckBox(AddInv)
        self.checkKeep.setObjectName("checkKeep")
        self.horizontalLayout_2.addWidget(self.checkKeep)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.x_label = QtWidgets.QLabel(AddInv)
        self.x_label.setObjectName("x_label")
        self.horizontalLayout.addWidget(self.x_label)
        self.xEdit = QtWidgets.QLineEdit(AddInv)
        self.xEdit.setObjectName("xEdit")
        self.horizontalLayout.addWidget(self.xEdit)
        self.y_label = QtWidgets.QLabel(AddInv)
        self.y_label.setObjectName("y_label")
        self.horizontalLayout.addWidget(self.y_label)
        self.yEdit = QtWidgets.QLineEdit(AddInv)
        self.yEdit.setObjectName("yEdit")
        self.horizontalLayout.addWidget(self.yEdit)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(AddInv)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(AddInv)
        self.buttonBox.accepted.connect(AddInv.accept)
        self.buttonBox.rejected.connect(AddInv.reject)
        QtCore.QMetaObject.connectSlotsByName(AddInv)

    def retranslateUi(self, AddInv):
        _translate = QtCore.QCoreApplication.translate
        AddInv.setWindowTitle(_translate("AddInv", "Add invariant point"))
        self.label.setText(_translate("AddInv", "Label"))
        self.checkKeep.setText(_translate("AddInv", "Keep results"))
        self.x_label.setText(_translate("AddInv", "X"))
        self.y_label.setText(_translate("AddInv", "Y"))

