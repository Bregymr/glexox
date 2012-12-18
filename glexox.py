#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import serial
import array
import numpy
import os
import re
from PyQt4 import Qt, QtGui, QtCore
import PyQt4.Qwt5 as Qwt
from datetime import datetime
import commands

#TODO: Properly detect "finger out" condition
#TODO: Alarm features
#TODO: Eliminate heartbeat double-tap
#TODO: Make things better
#TODO: Make things less bad
#TODO: Improve things

class CMS50D(object):
	#TODO: Properly decode "finger out" flag, assuming it exists
	def __init__(self, portstr):
		self.port = serial.Serial(portstr, 19200, timeout=0, stopbits=1, parity=serial.PARITY_ODD, bytesize=8)
		self.current_bpm = None
		self.current_spo2 = None
		self._buf = array.array('B')
	def get_data(self):
		self._buf.fromstring(self.port.read(128))
		data = []
		i = 0
		state = 0
		lvl = 0
		pulse = 0
		blip = 0
		ox = 0
		while (len(self._buf) >= (5 - state)):
			b = self._buf.pop(0)
			if state == 0:
				if b & 0x80 == 0x80:
					if (b & 0x40):
						blip = 1
					else:
						blip = 0
					state = 1
			elif state == 1:
				lvl = b
				state = 2
			elif state == 2:
				if (b & 0x40):
					pulse = 128
				else:
					pulse = 0
				state = 3
			elif state == 3:
				pulse += b
				state = 4
			elif state == 4:
				ox = b
				data.append((lvl,blip,pulse,ox))
				state = 0
		return data
	def close(self):
		self.port.close()

class PulseOxGui(QtGui.QMainWindow):
	class ConfigForm(QtGui.QWidget):
		class PortSelector(QtGui.QWidget):
			tty_pfxs = ("ttyUSB",)
			def __init__(self, *args):
				QtGui.QWidget.__init__(self, *args)
				self.setLayout(QtGui.QHBoxLayout())
				self.layout().setContentsMargins(0,0,0,0)
				self._combo = QtGui.QComboBox()
				self._button = QtGui.QPushButton("...")
				self.layout().addWidget(self._combo, 1)
				self.layout().addWidget(self._button, 0)
				self.rescan()
				self.connect(self._button, QtCore.SIGNAL("clicked()"), self.show_prompt)
			def value(self):
				return self._combo.itemText(self._combo.currentIndex())
			def set_value(self, text):
				found = False
				for i in range(self._combo.count()):
					if self._combo.itemText(i) == text:
						self._combo.setCurrentIndex(i)
						found = True
						break
				if not found:
					self.set_custom(text)
			def set_custom(self, text):
				if self._custom_port:
					self._combo.removeItem(0)
				self._combo.insertItem(0, text)
				self._combo.setCurrentIndex(0)
				self._custom_port = True
			def show_prompt(self):
				text, ok = QtGui.QInputDialog.getText(self, "Custom entry", "Port", text="/dev/")
				if ok:
					self.set_custom(text)
			def rescan(self):
				self._combo.clear()
				self._custom_port = False
				for x in os.listdir("/dev/"):
					for y in self.tty_pfxs:
						if x[:len(y)] == y:
							self._combo.addItem("/dev/" + x)
							break
				#TODO: add Windows-compatible portscan
		class DirSelector(QtGui.QWidget):
			def __init__(self, *args):
				QtGui.QWidget.__init__(self, *args)
				self.setLayout(QtGui.QHBoxLayout())
				self.layout().setContentsMargins(0,0,0,0)
				self._box = QtGui.QLineEdit()
				self._button = QtGui.QPushButton("...")
				self.layout().addWidget(self._box, 1)
				self.layout().addWidget(self._button, 0)
				self.connect(self._button, QtCore.SIGNAL("clicked()"), self.show_prompt)
			def value(self):
				return self._box.text()
			def set_value(self, value):
				self._box.setText(value)
			def show_prompt(self):
				d = QtGui.QFileDialog.getExistingDirectory(self, "Select log storage directory")
				if len(d) > 0:
					self._box.setText(d)
		def __init__(self, *args):
			QtGui.QWidget.__init__(self, *args)
			self.setWindowTitle("GLExOx configuration")
			self.inp_hwtype = QtGui.QComboBox()
			self.inp_hwtype.addItem("Contec CMS50D+")
			self.inp_hwtype.setEnabled(False)
			self.inp_port = self.PortSelector()
			self.inp_logdir = self.DirSelector()
			self.inp_statlog_en = QtGui.QCheckBox("Record stats")
			self.inp_statlog_base = QtGui.QLineEdit()
			self.inp_ppglog_en = QtGui.QCheckBox("Record PPG waveform")
			self.inp_ppglog_base = QtGui.QLineEdit()
			self.inp_log_comment = QtGui.QTextEdit()
			self.inp_log_comment.setAcceptRichText(False)
			comms_grp = QtGui.QGroupBox("Hardware")
			comms_grp.setLayout(QtGui.QGridLayout())
			comms_grp.layout().addWidget(QtGui.QLabel("Device"),0,0)
			comms_grp.layout().addWidget(self.inp_hwtype,0,1)
			comms_grp.layout().addWidget(QtGui.QLabel("Port"),1,0)
			comms_grp.layout().addWidget(self.inp_port,1,1)
			logging_grp = QtGui.QGroupBox("Data logging")
			logging_grp.setLayout(QtGui.QGridLayout())
			logging_grp.layout().addWidget(QtGui.QLabel("Log directory"),0,0)
			logging_grp.layout().addWidget(self.inp_logdir,0,1)
			logging_grp.layout().addWidget(self.inp_statlog_en,1,0,1,2)
			logging_grp.layout().addWidget(QtGui.QLabel("Stats filename prefix"),2,0)
			logging_grp.layout().addWidget(self.inp_statlog_base,2,1)
			logging_grp.layout().addWidget(self.inp_ppglog_en,3,0,1,2)
			logging_grp.layout().addWidget(QtGui.QLabel("PPG filename prefix"),4,0)
			logging_grp.layout().addWidget(self.inp_ppglog_base,4,1)
			logging_grp.layout().addWidget(QtGui.QLabel("Log comments"),5,0)
			logging_grp.layout().addWidget(self.inp_log_comment,5,1)
			self.buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Apply | QtGui.QDialogButtonBox.Reset)
			self.setLayout(QtGui.QVBoxLayout())
			self.layout().addWidget(comms_grp)
			self.layout().addWidget(logging_grp)
			self.layout().addWidget(self.buttons)
			self.connect(self.buttons.button(self.buttons.Ok), QtCore.SIGNAL("clicked()"), self.close)
			self.connect(self.buttons.button(self.buttons.Ok), QtCore.SIGNAL("clicked()"), self.commit)
			self.connect(self.buttons.button(self.buttons.Apply), QtCore.SIGNAL("clicked()"), self.commit)
			self.connect(self.buttons.button(self.buttons.Cancel), QtCore.SIGNAL("clicked()"), self.reset)
			self.connect(self.buttons.button(self.buttons.Cancel), QtCore.SIGNAL("clicked()"), self.close)
			self.settings = {
				"log_dir": os.getenv("HOME"),
				"statlog_base": "stats",
				"ppglog_base": "pleth",
				"statlog_en": False,
				"ppglog_en": False,
				"log_comment": None,
				"port": str(self.inp_port.value()),
				}
			self.reset()
		def commit(self):
			self.settings["port"] = str(self.inp_port.value())
			self.settings["log_dir"] = str(self.inp_logdir.value())
			self.settings["statlog_en"] = self.inp_statlog_en.isChecked()
			self.settings["ppglog_en"] = self.inp_ppglog_en.isChecked()
			self.settings["statlog_base"] = str(self.inp_statlog_base.text())
			self.settings["ppglog_base"] = str(self.inp_ppglog_base.text())
			self.settings["log_comment"] = str(self.inp_log_comment.toPlainText()).strip() or None
			self.emit(QtCore.SIGNAL("new_config"))
		def reset(self):
			if "port" in self.settings:
				self.inp_port.set_value(self.settings["port"])
			self.inp_logdir.set_value(self.settings["log_dir"])
			self.inp_statlog_en.setChecked(self.settings["statlog_en"])
			self.inp_ppglog_en.setChecked(self.settings["ppglog_en"])
			self.inp_statlog_base.setText(self.settings["statlog_base"])
			self.inp_ppglog_base.setText(self.settings["ppglog_base"])
			self.inp_log_comment.setText(self.settings["log_comment"] or "")
		def lock_settings(self, lock):
			if lock:
				self.buttons.button(self.buttons.Ok).setEnabled(False)
				self.buttons.button(self.buttons.Apply).setEnabled(False)
			else:
				self.buttons.button(self.buttons.Ok).setEnabled(True)
				self.buttons.button(self.buttons.Apply).setEnabled(True)
	class DisplayForm(QtGui.QWidget):
		class DataPlot(Qwt.QwtPlot):
			def __init__(self, *args):
				Qwt.QwtPlot.__init__(self, *args)
				self.setCanvasBackground(Qt.Qt.black)
				self.x = range(0,250)
				self.y = numpy.zeros(len(self.x))
				self.curves = (Qwt.QwtPlotCurve(),Qwt.QwtPlotCurve())
				for n in (0,1):
					pen = QtGui.QPen()
					pen.setWidth(3)
					pen.setColor(QtGui.QColor(255-127*n,255-127*n,0))
					self.curves[n].setPen(pen)
					self.curves[n].attach(self)
				self.enableAxis(Qwt.QwtPlot.yLeft,False)
				self.enableAxis(Qwt.QwtPlot.xBottom,False)
				self.setAxisScale(Qwt.QwtPlot.yLeft,0,127)
				self.setAxisScale(Qwt.QwtPlot.xBottom,0,250)
				self.i = 0
			def add_data(self, newdata):
				for x in newdata:
					self.y[self.i] = x
					self.i += 1
					if self.i >= len(self.y):
						self.i = 0
				self.curves[0].setData(self.x[:self.i], self.y[:self.i])
				self.curves[1].setData(self.x[self.i+25:], self.y[self.i+25:])
		class NumLabel(QtGui.QFrame):
			class ValueLabel(QtGui.QLabel):
				def __init__(self, *args):
					QtGui.QLabel.__init__(self, *args)
					self.font().setFixedPitch(True)
					self.setMinimumSize(64,64)
				def resizeEvent(self, foo):
					foo = self.font()
					foo.setPixelSize(self.height()*3/4)
					self.setFont(foo)
			def __init__(self, name_text="", *args):
				QtGui.QFrame.__init__(self, *args)
				self.setFrameShape(QtGui.QFrame.StyledPanel)
				self.setFrameShadow(QtGui.QFrame.Sunken)
				self.font().setFixedPitch(True)
				self.name_label = QtGui.QLabel(name_text)
				self.name_label.setAlignment(Qt.Qt.AlignLeft | Qt.Qt.AlignTop)
				self.value_label = self.ValueLabel("?")
				self.value_label.setAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
				self.layout = QtGui.QVBoxLayout()
				self.layout.addWidget(self.name_label,1)
				self.layout.addWidget(self.value_label,8)
				self.setLayout(self.layout)
			def setText(self, *args):
				self.value_label.setText(*args)
		class Winkenlight(QtGui.QWidget):
			on_color = (255,90,90)
			off_color = (80,0,0)
			def __init__(self, *args):
				QtGui.QWidget.__init__(self, *args)
				self.setMinimumSize(30,30)
				self._pen = Qt.QPen()
				self._pen.setWidth(5)
				self._brush = QtGui.QBrush(QtGui.QColor(255,255,0))
				self._ts = QtCore.QDateTime.currentDateTime().toPyDateTime()
				self._cold = (self.on_color[0]-self.off_color[0], self.on_color[1]-self.off_color[1], self.on_color[2]-self.off_color[2])
			def resizeEvent(self, foo):
				self.update()
			def paintEvent(self, foo):
				td = QtCore.QDateTime.currentDateTime().toPyDateTime() - self._ts
				lum = pow(.67,pow((td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6)/75000.,1.33))
				r = int(self.off_color[0] + lum*self._cold[0])
				g = int(self.off_color[1] + lum*self._cold[1])
				b = int(self.off_color[2] + lum*self._cold[2])
				self._brush.setColor(QtGui.QColor(r,g,b))
				self._pen.setColor(QtGui.QColor(r*2/3,g*2/3,b*2/3))
				p = QtGui.QPainter(self)
				diam = min(self.width(),self.height()) * 2 / 3
				x = (self.width()-diam)/2
				y = (self.height()-diam)/2
				p.setPen(self._pen)
				p.setBrush(self._brush)
				p.drawEllipse(x,y,diam,diam)
			def ping(self):
				self._rgb = list(self.on_color)
				self._ts = QtCore.QDateTime.currentDateTime().toPyDateTime()
		def __init__(self, *args):
			QtGui.QWidget.__init__(self, *args)
			self.plot = self.DataPlot()
			self.blinker = self.Winkenlight()
			self.ox_label = self.NumLabel(name_text = "SpO<sub>2</sub> (%)")
			self.ox_avg_label = self.NumLabel(name_text = "SpO<sub>2</sub> (%), 1-min. avg.")
			self.hr_label = self.NumLabel(name_text = "HR (bpm)")
			self.hr_avg_label = self.NumLabel(name_text = "HR (bpm), 1-min. avg.")
			self.lo_top = QtGui.QHBoxLayout()
			self.lo_top.addWidget(self.ox_label)
			self.lo_top.addWidget(self.ox_avg_label)
			self.lo_top.addWidget(self.hr_label)
			self.lo_top.addWidget(self.hr_avg_label)
			self.lo_bottom = QtGui.QHBoxLayout()
			self.lo_bottom.addWidget(self.plot, 9)
			self.lo_bottom.addWidget(self.blinker, 1)
			self.lo_outer = QtGui.QVBoxLayout()
			self.lo_outer.addLayout(self.lo_top, 1)
			self.lo_outer.addLayout(self.lo_bottom, 1)
			self.setLayout(self.lo_outer)
	class Toolbar(QtGui.QToolBar):
		class StartStopAction(QtGui.QAction):
			def disable(self):
				self.setEnabled(False)
			def enable(self):
				self.setEnabled(True)
		def __init__(self, *args):
			QtGui.QToolBar.__init__(self, *args)
			self.start = self.StartStopAction("Start", None)
			self.stop = self.StartStopAction("Stop", None)
			self.stop.setEnabled(False)
			self.config = QtGui.QAction("Setup...", None)
			self.reset = QtGui.QAction("Stat reset", None)
			self.quit = QtGui.QAction("Quit", None)
			self.connect(self.start, QtCore.SIGNAL("triggered()"), self.start.disable)
			self.connect(self.stop, QtCore.SIGNAL("triggered()"), self.stop.disable)
			self.addAction(self.start)
			self.addAction(self.stop)
			self.addAction(self.reset)
			self.addSeparator()
			self.addAction(self.config)
			self.addSeparator()
			self.addAction(self.quit)
	def __init__(self, *args):
		QtGui.QMainWindow.__init__(self, *args)
		self.setWindowTitle("GLExOx pulse oximeter display")
		self.display_form = self.DisplayForm()
		self.config_form = self.ConfigForm()
		self.setCentralWidget(self.display_form)
		self.toolbar = self.Toolbar()
		self.addToolBar(self.toolbar)
		self.connect(self.toolbar.quit, QtCore.SIGNAL("triggered()"), self.quit)
		self.connect(self.toolbar.start, QtCore.SIGNAL("triggered()"), self._start)
		self.connect(self.toolbar.stop, QtCore.SIGNAL("triggered()"), self._stop)
		self.connect(self.toolbar.config, QtCore.SIGNAL("triggered()"), self.config_form.show)
		self.connect(self.config_form, QtCore.SIGNAL("new_config"), self.update_config)
		self.statusBar()
	def update_config(self):
		self.emit(QtCore.SIGNAL("new_portstr"), self.config_form.settings["port"])
		self.emit(QtCore.SIGNAL("new_log_comment"), self.config_form.settings["log_comment"])
	def update_running(self, running):
		if running:
			self.config_form.lock_settings(True)
			self.toolbar.stop.enable()
		else:
			self.config_form.lock_settings(False)
			self.toolbar.start.enable()
	def update_stats(self, hr, ox):
		self.display_form.ox_label.setText(str(ox))
		self.display_form.hr_label.setText(str(hr))
	def update_plot(self, newdata):
		self.display_form.plot.add_data(newdata)
	def blink(self):
		self.display_form.blinker.ping()
	def refresh(self):
		self.display_form.blinker.update()
		self.display_form.plot.replot()
	def show_message(self, msg):
		self.statusBar().showMessage(msg)
	def show_error(self, msg):
		QtGui.QMessageBox.critical(self, "Error", msg)
	def closeEvent(self, foo):
		self.quit()
	def _start(self):
		self.update_config()
		if self.config_form.settings["statlog_en"] or self.config_form.settings["ppglog_en"]:
			suffix = datetime.now().strftime('_%Y-%m-%d_%H-%M-%S.csv')
			ppglog_path = os.path.join(self.config_form.settings["log_dir"],self.config_form.settings["ppglog_base"] + suffix)
			statlog_path = os.path.join(self.config_form.settings["log_dir"],self.config_form.settings["statlog_base"] + suffix)
		self.emit(QtCore.SIGNAL("new_statlog_path"), self.config_form.settings["statlog_en"] and statlog_path or None)
		self.emit(QtCore.SIGNAL("new_ppglog_path"), self.config_form.settings["ppglog_en"] and ppglog_path or None)
		self.emit(QtCore.SIGNAL("start"))
	def _stop(self):
		self.emit(QtCore.SIGNAL("stop"))
	def quit(self):
		self.emit(QtCore.SIGNAL("quit"))

class Logger(object):
	@staticmethod
	def timestr(dt):
		td = (dt - datetime.fromtimestamp(0))
		return "{0:d}.{1:06}".format(td.seconds + td.days * 24 * 3600,td.microseconds)
	def write(self, *args, **kwargs):
		return self._fd.write(*args, **kwargs)
	def write_row(self, cols):
		return self.write(",\t".join(map(str, cols)) + "\n")
	def __init__(self, path, tstamp, head_text = None):
		self._fd = open(path, "w")
		self.write("# " + self.timestr(tstamp) + "\n")
		if head_text:
			self.write("# " + re.sub(r'\n',r'\n# ',head_text.strip()) + "\n\n")
	def close(self):
		self._fd.close()

class StatLog(Logger):
	def __init__(self, *args, **kwargs):
		Logger.__init__(self, *args, **kwargs)
		self.write_row(("Time","SpO2(%)","HR(bpm)"))
	def append(self, dt, ox, hr):
		self.write_row((self.timestr(dt),ox,hr))

class PPGLog(Logger):
	def __init__(self, *args, **kwargs):
		Logger.__init__(self, *args, **kwargs)
		self.write_row(("Seq","Value"))
		self.i = 0
	def append(self, value):
		self.write_row((self.i, value))
		self.i += 1

class Core(Qt.QObject):
	interval = 25
	def __init__(self, *args):
		Qt.QObject.__init__(self, *args)
		self._hr = None
		self._ox = None
		self._podev = None
		self._beat = False
		self.timer_id = None
		self.portstr = None
		self.statlog_path = None
		self.ppglog_path = None
		self.log_comment = None
		self._ppglog = None
		self._statlog = None
	def set_portstr(self, path):
		self.portstr = path
	def set_statlog_path(self, path):
		self.statlog_path = path
	def set_ppglog_path(self, path):
		self.ppglog_path = path
	def set_log_comment(self, text):
		self.log_comment = text
	def _start_failed(self,msg):
		self.emit(QtCore.SIGNAL("error"),msg)
		self.emit(QtCore.SIGNAL("new_status"), "Failed to start.")
		self.emit(QtCore.SIGNAL("running"), False)
	def start(self):
		if self.portstr in (None,""):
			return self._start_failed("No port specified!")
		if self._podev != None:
			self.stop()
		if self.ppglog_path or self.statlog_path:
			dt = datetime.now()
		if self.ppglog_path:
			try:
				self._ppglog = PPGLog(self.ppglog_path, dt, self.log_comment)
				print dt.isoformat(' ') + ": Logging PPG waveform to " + self.ppglog_path
			except IOError, ex:
				return self._start_failed("Couldn't write pleth log file:\n" + str(ex))
		else:
			self._ppglog = None
		if self.statlog_path:
			try:
				self._statlog = StatLog(self.statlog_path, dt, self.log_comment)
				print dt.isoformat(' ') + ": Logging stats to " + self.statlog_path
			except IOError, ex:
				return self._start_failed("Couldn't write stat log file:\n" + str(ex))
		else:
			self._statlog = None
		try:
			self._podev = CMS50D(self.portstr)
		except serial.serialutil.SerialException, ex:
			return self._start_failed("Couldn't connect to device:\n" + str(ex))
		self.emit(QtCore.SIGNAL("new_status"), "Running.")
		self.emit(QtCore.SIGNAL("running"), True)
		self.timer_id = self.startTimer(self.interval)
	def stop(self):
		if self._podev != None:
			self._podev.close()
			self._podev = None
		if self.timer_id:
			self.killTimer(self.timer_id)
		if self._ppglog:
			self._ppglog.close()
			self._ppglog = None
		if self._statlog:
			self._statlog.close()
			self._statlog = None
		self.emit(QtCore.SIGNAL("new_status"), "Stopped.")
		self.emit(QtCore.SIGNAL("running"), False)
	def timerEvent(self, foo):
		try:
			data = self._podev.get_data()
		except Exception, ex:
			self.stop()
			self.emit(QtCore.SIGNAL("error"),"Error reading data:\n" + str(ex))
			self.emit(QtCore.SIGNAL("new_status"), "Stopped due to error.")
			return
		if data:
			lvls, beats = zip(*data)[0:2]
			if self._ppglog:
				for lvl in lvls:
					self._ppglog.append(lvl)
			if self._beat:
				self._beat = False
			else:
				if 1 in beats:
					self._beat = True
					self.emit(QtCore.SIGNAL("heartbeat"))
			hr, ox = data[-1][2:4]
			if (hr != self._hr) or (ox != self._ox):
				self._hr = hr
				self._ox = ox
				if self._statlog:
					self._statlog.append(datetime.now(), ox, hr)
				self.emit(QtCore.SIGNAL("new_stats"), hr, ox)
			self.emit(QtCore.SIGNAL("new_plotdata"), lvls)
		self.emit(QtCore.SIGNAL("tick"))
	def reset_stats(self):
		self._hr_samples = self._hr and [self._hr] or []
		self._ox_samples = self._ox and [self._ox] or []
	#FIXME: These should be TIME-averaged. Simply taking the mean of the last n samples may produce a misleading result.
	def get_avg_hr(self):
		return numpy.mean(self._hr_samples)
	def get_avg_ox(self):
		return numpy.mean(self._ox_samples)
	def quit(self):
		self.stop()
		self.emit(QtCore.SIGNAL("quit"))

def main(args): 
	app = Qt.QApplication(args)
	gui = PulseOxGui()
	gui.resize(640,480)
	gui.show()
	core = Core()
	app.connect(core, QtCore.SIGNAL("new_stats"), gui.update_stats)
	app.connect(core, QtCore.SIGNAL("new_status"), gui.show_message)
	app.connect(core, QtCore.SIGNAL("heartbeat"), gui.blink)
	app.connect(core, QtCore.SIGNAL("new_plotdata"), gui.update_plot)
	app.connect(core, QtCore.SIGNAL("tick"), gui.refresh)
	app.connect(core, QtCore.SIGNAL("running"), gui.update_running)
	app.connect(core, QtCore.SIGNAL("error"), gui.show_error)
	app.connect(gui, QtCore.SIGNAL("start"), core.start)
	app.connect(gui, QtCore.SIGNAL("stop"), core.stop)
	app.connect(gui, QtCore.SIGNAL("quit"), core.quit)
	app.connect(gui, QtCore.SIGNAL("new_portstr"), core.set_portstr)
	app.connect(gui, QtCore.SIGNAL("new_statlog_path"), core.set_statlog_path)
	app.connect(gui, QtCore.SIGNAL("new_ppglog_path"), core.set_ppglog_path)
	app.connect(gui, QtCore.SIGNAL("new_log_comment"), core.set_log_comment)
	app.connect(core, QtCore.SIGNAL("quit"), app.quit)
	sys.exit(app.exec_())

if __name__ == '__main__':
	main(sys.argv)
