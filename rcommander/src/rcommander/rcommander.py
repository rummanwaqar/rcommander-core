import roslib; roslib.load_manifest('rcommander')
import rospy
import sys
import time
from PyQt4 import QtGui
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from nodebox.gui.qt import NodeBoxGraphicsView 
from nodebox import graphics
from nodebox.graphics.qt import *
import graph
import graph.style as gs
import graph.layout as gl
import math
#import pdb
import tf
import smach
import smach_ros
import threading
from rcommander_auto import Ui_RCommanderWindow
#import cPickle as pk
import os.path as pt
#import os
#import glob
#import ctypes
import copy
import numpy as np

#Import tools
import pr2_utils as pu
import graph_model as gm
import sm_thread_runner as smtr
import tool_utils as tu
import navigate_tool as nt
import tuck_tool as tt
import outcome_tool as ot
import gripper_tool as gt
import linear_move_tool as lmt
import point_tool as ptl
import gripper_event_tool as get
import sleep_tool as st
import speak_tool as skt
import move_arm_tool as mat
import move_tool as mt
import spine_tool as spt
import state_machine_tool as smt


def split(num, factor):
    num1 = int(round(num * factor))
    num2 = num - num1
    return [num1, num2]


class RNodeBoxBaseClass(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_RCommanderWindow()
        self.ui.setupUi(self)

        #Setup QGraphicsView
        #From NodeBoxDocumentBaseClass
        superView = self.ui.graphicsSuperView
        superView._scene = scene = QGraphicsScene()
        scene.setItemIndexMethod(QGraphicsScene.NoIndex)
        superView.setScene(scene)

        self.graphicsView = graphicsView = NodeBoxGraphicsView()
        scene.addItem(graphicsView)
        graphicsView._scene = scene
        graphicsView.superView = superView
        graphicsView._viewPort = superView.viewport()
        self.graphicsView.document = self
        self.currentView = self.graphicsView

        #Setup NB classes
        #from NodeBoxDocument
        self.namespace = {}
        textScaleFactor = QPixmap(1, 1).logicalDpiX() / 72.0
        self.canvas = graphics.Canvas()
        self.canvas._setTextScaleFactor(textScaleFactor)
        self.context = graphics.Context(self.canvas, self.namespace)

        #from NodeBoxDocument
        # _initNamespace
        self._pageNumber = 1
        self.__doc__ = {}
        self._frame = 150
        self._seed = time.time()
        self.animationTimer = None
        self.speed = 30.

        self.namespace["_ctx"] = self.context
        for attrName in dir(self.context):
            self.namespace[attrName] = getattr(self.context, attrName)
        self.namespace["__doc__"] = self.__doc__
        self.namespace["PAGENUM"] = self._pageNumber
        self.namespace["FRAME"] = self._frame

        #Setup the scene
        self._setup_draw(self.setup)

        #Start animation loop
        self.speed = self.canvas.speed
        self.animationTimer = QTimer(self)
        self.connect(self.animationTimer, SIGNAL("timeout()"), self.animation_cb)
        self.animationTimer.start(1000.0 / self.speed)
        #self.connect(self.ui.graphicsSuperView, SIGNAL('resizeEvent(QResizeEvent*)'), self.resize_view_cb)
        #self.connect(self.graphicsView, SIGNAL("mousePressEvent(QMouseEvent *)"), self.mouse_pressed_cb)

    #def mouse_pressed_cb(self, event):
    #    print 'Got called!'

    #def resize_view_cb(self):
    #    print 'resized'

        #self.zoomLevel = self.ui.zoomLevel
        #self.zoomSlider = self.ui.zoomSlider
        #self.connect(self.ui.zoomSlider, SIGNAL('valueChanged(int)'), self.dragZoom)

    def dragZoom(self):
        self.graphicsView.dragZoom_(self.ui.zoomSlider.value())

    def _setup_draw(self, fn):
        #from fastRun
        #print 'se',
        self.canvas.clear()
        pos = self.currentView.mousePosition
        mx, my = pos.x(), pos.y()

        #dclick_pos = self.currentView.mouseDCPosition
        #dcx, dcy = dclick_pos.x(), dclick_pos.y()
        self.namespace["MOUSEX"], self.namespace["MOUSEY"] = mx, my
        #self.namespace["MOUSEDX"], self.namespace["MOUSEDY"] = dcx, dcy
        self.namespace["mousedoubleclick"] = self.currentView.mousedoubleclick
        self.currentView.mousedoubleclick = False
        self.namespace["mousedown"] = self.currentView.mousedown
        self.namespace["rightdown"] = self.currentView.rightdown
        self.namespace["keydown"] = self.currentView.keydown
        self.namespace["key"] = self.currentView.key
        self.namespace["keycode"] = self.currentView.keycode
        self.namespace["scrollwheel"] = self.currentView.scrollwheel
        self.namespace["wheeldelta"] = self.currentView.wheeldelta
        self.namespace['PAGENUM'] = self._pageNumber
        self.namespace['FRAME'] = self._frame
        self.currentView.scrollwheel = False
        self.currentView.wheeldelta = 0
        #print 't',
        for k in self.namespace.keys():
            exec "global %s\n" % (k)
            exec "%s = self.namespace['%s']" % (k, k)
        fn()
        #print 'u',
        self.currentView.canvas = self.canvas
        #print 'p',

    def animation_cb(self):
        self._setup_draw(self.draw)
        #print 'ed'
        
    def stop(self):
        if self.animationTimer is not None:
            self.animationTimer.stop()
            self.animationTimer = None
        QApplication.restoreOverrideCursor()


def copy_style(astyle, bstyle):
    bstyle.background  = astyle.background  
    bstyle.fill        = astyle.fill       
    bstyle.stroke      = astyle.stroke     
    bstyle.strokewidth = astyle.strokewidth
    bstyle.text        = astyle.text       
    bstyle.font        = astyle.font       
    bstyle.fontsize    = astyle.fontsize   
    bstyle.textwidth   = astyle.textwidth  
    bstyle.align       = astyle.align      
    bstyle.depth       = astyle.depth      


class FSMStackElement:

    def __init__(self, model, view, node):
        self.model = model
        self.view = view
        self.graph_node = None
        self.node = node


##
# keeps track of smach state machine, makes sure it is consistent with (G,V) representation
# model at this level has (V,E) reprentation
class RCommanderWindow(RNodeBoxBaseClass):

    def __init__(self):
        RNodeBoxBaseClass.__init__(self)
        self.connect(self.ui.run_button,         SIGNAL('clicked()'), self.run_cb)
        self.connect(self.ui.add_button,         SIGNAL('clicked()'), self.add_cb)
        self.connect(self.ui.reset_button,       SIGNAL('clicked()'), self.reset_cb)
        self.connect(self.ui.save_button,        SIGNAL('clicked()'), self.save_cb)
        self.connect(self.ui.start_state_button, SIGNAL('clicked()'), self.start_state_cb)

        self.connect(self.ui.delete_button, SIGNAL('clicked()'), self.delete_cb)
        self.connect(self.ui.action_Run, SIGNAL('triggered(bool)'), self.run_sm_cb)
        self.connect(self.ui.action_stop, SIGNAL('triggered(bool)'), self.stop_sm_cb)
        self.connect(self.ui.actionNew, SIGNAL('triggered(bool)'), self.new_sm_cb)
        self.connect(self.ui.action_save, SIGNAL('triggered(bool)'), self.save_sm_cb)
        self.connect(self.ui.action_save_as, SIGNAL('triggered(bool)'), self.save_as_sm_cb)
        self.connect(self.ui.action_open, SIGNAL('triggered(bool)'), self.open_sm_cb)
        self.ui.splitter.setSizes(split(self.width(), .83))

        self.empty_container(self.ui.properties_tab)
        self.empty_container(self.ui.connections_tab)
        self.add_mode()
        self.disable_buttons()

        #create instance variables
        self.tabs = {}
        self.tool_dict = {}
        self.selected_tool = None
        #Name of currently selected tool that operates on graph
        self.selected_graph_tool = None 
        self.selected_node = None
        self.selected_edge = None
        #self.tool_dict['add_edge'] = {}

        self.fsm_stack = []
        #self.document = gm.FSMDocument.new_document()
        #self.current_sm_threads = {}
        #self.current_graph_name = 'untitled_fsm'

        self.status_bar_timer = QTimer()
        self.connect(self.status_bar_timer, SIGNAL('timeout()'), self.status_bar_check)
        self.status_bar_timer.start(100)
        #self.set_selected_node('start')
        #self.node_cb(self.graph_model.node('start'))
        
        #ROS things
        print 'ros things'
        rospy.init_node('rcommander', anonymous=True)
        print 'tf'
        self.tf_listener = tf.TransformListener()
        print 'pr2'
        self.pr2 = pu.PR2(self.tf_listener)
        print 'don pr2'


    def status_bar_check(self):
        if self.graph_model.sm_thread.has_key('run_sm'):
            sm_thread = self.graph_model.sm_thread['run_sm']

            if sm_thread.exception != None:
                m = sm_thread.exception.message
                self.statusBar().showMessage('%s: %s' % (sm_thread.exception.__class__, m), 15000)
                self.graph_model.sm_thread.pop('run_sm')
                self.graph_model.sm_thread.pop('preempted')
                return

            if sm_thread.outcome != None:
                self.statusBar().showMessage('Finished with outcome: %s' % sm_thread.outcome, 15000)
                self.graph_model.sm_thread.pop('run_sm')
                self.graph_model.sm_thread.pop('preempted')
                return

            if not sm_thread.isAlive():
                self.statusBar().showMessage('Error: SM thread unexpectedly died.', 15000)
                self.graph_model.sm_thread.pop('run_sm')
                self.graph_model.sm_thread.pop('preempted')
                return

            if self.graph_model.sm_thread['preempted'] != None and (time.time() - self.graph_model.sm_thread['preempted'] > 5.):
                rospy.loginfo('Thread took too long to terminate.  Escallating and using exception exit.')
                self.graph_model.sm_thread['run_sm'].except_preempt()
                rospy.loginfo('Thread terminated.')
                self.graph_model.sm_thread.pop('run_sm')
                self.graph_model.sm_thread.pop('preempted')

            rstring = 'Running...'
            if str(self.statusBar().currentMessage()) != rstring:
                self.statusBar().showMessage(rstring, 1000)

    def _create_tab(self, tab_name):
        ntab = QWidget()
        ntab.setObjectName(tab_name)
        QHBoxLayout(ntab)
        self.ui.tools_box.addTab(ntab, tab_name)
        self.ui.tools_box.setTabText(self.ui.tools_box.indexOf(ntab), tab_name)
        self.tabs[tab_name] = ntab

    ##
    # Should only be called once during initialization
    #
    # @param list of [tab-name, tool-object] pairs
    def add_tools(self, tools_list):
        #add tools to the right tab, creating tabs if needed
        self.button_group_tab = QButtonGroup()
        for tab_name, tool in tools_list:
            if not self.tabs.has_key(tab_name):
                self._create_tab(tab_name)
            tab_widget = self.tabs[tab_name]
            self.button_group_tab.addButton(tool.create_button(tab_widget))
            #self.tool_dict[tool.get_name()] = {'tool_obj': tool}
            self.tool_dict[tool.get_smach_class()] = {'tool_obj': tool}

        for tname in self.tabs.keys():
            self.tabs[tname].update()

        #Outcome tool is a specialized built in tool
        self.button_group_tab.addButton(self.ui.add_outcome_button)
        outcome_tool = ot.OutcomeTool(self.ui.add_outcome_button, self)
        #self.tool_dict[outcome_tool.get_name()] = {'tool_obj': outcome_tool}
        self.tool_dict[outcome_tool.get_smach_class()] = {'tool_obj': outcome_tool}


        #print '>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>'
        #print '>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>'
        #for k in self.tool_dict.keys():
        #    print k
        #print '22222222222222222222222222222222222222222'
        #print '22222222222222222222222222222222222222222'

    def current_children_of(self, node_name):
        return self.graph_model.current_children_of(node_name)

    def connectable_nodes(self, node_name, outcome):
        return self.graph_model.connectable_nodes(node_name, outcome)

    def global_nodes(self, class_filter):
        return self.graph_model.global_nodes(class_filter)

    def set_selected_node(self, name):
        self.selected_node = name

    def set_selected_edge(self, n1, n2, label):
        if n1 == None:
            self.selected_edge = None
        else:
            self.selected_edge = self.graph_model.edge(n1, n2, label=label)

    def empty_container(self, pbox): 
        #pbox = self.ui.properties_tab
        formlayout = pbox.layout()
        for i in range(formlayout.count()):
            item = formlayout.itemAt(0)
            formlayout.removeItem(item)
        children = pbox.children()
        for c in children[1:]:
            formlayout.removeWidget(c)
            c.setParent(None)
        formlayout.invalidate()
        pbox.update()

    def set_selected_tool(self, tool_name):
        self.selected_tool = tool_name
        #TODO: disable buttons

    def run_state_machine(self, sm):
        if self.graph_model.sm_thread.has_key('run_sm'):
            raise RuntimeError('Only state machine execution thread maybe be active at a time.')
        self.graph_model.run(self.graph_model.document.get_name(), state_machine=sm)
        #sm = graph_model.create_state_machine()
        #self.graph_model.run()
        #rthread = smtr.ThreadRunSM(self.document.get_name(), sm)
        #rthread.start()
        #self.sm_thread['run_sm'] = rthread
        #self.sm_thread['preempted'] = None

    #####################################################################
    # Callbacks
    #####################################################################
    def save_as_sm_cb(self):
        #popup file dialog
        filename = str(QFileDialog.getSaveFileName(self, 'Save As', self.graph_model.document.get_filename()))

        #user canceled
        if len(filename) == 0:
            return False

        if pt.exists(filename):
            #Ask if want to over write
            msg_box = QMessageBox()
            msg_box.setText('There is already a file with this name.')
            msg_box.setInformativeText('Do you want to overwrite it?')
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            msg_box.setDefaultButton(QMessageBox.Cancel)
            ret = msg_box.exec_()
            if ret == QMessageBox.No or ret == QMessageBox.Cancel:
                return False

        self.graph_model.save(filename)
        self.graph_model.document.set_filename(filename)
        self.graph_model.document.real_filename = True
        self.graph_model.document.modified = False
        return True

    def save_sm_cb(self):
        #print 'has real filename?', self.document.has_real_filename()
        if self.graph_model.document.has_real_filename():
            self.graph_model.save(self.graph_model.document.get_filename())
            return True
        else:
            return self.save_as_sm_cb()

    def new_sm_cb(self):
        #prompt user to save if document has been modifid
        if not self.check_current_document():
            return

        self._set_model(gm.GraphModel())
        self.nothing_cb(None)
        #self.document = FSMDocument.new_document()

    def check_current_document(self):
        if self.graph_model.document.modified:
            msg_box = QMessageBox()
            msg_box.setText('Current state machine has not been saved.')
            msg_box.setInformativeText('Do you want to save it first?')
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            msg_box.setDefaultButton(QMessageBox.Cancel)
            ret = msg_box.exec_()

            if ret == QMessageBox.Cancel:
                return False

            elif ret == QMessageBox.Yes:
                return self.save_sm_cb()

        return True

    def _reconnect_smach_states(self):
        for k in self.graph_model.smach_states:
            if hasattr(self.graph_model.smach_states[k], 'set_robot'):
                self.graph_model.smach_states[k].set_robot(self.pr2)

    def open_sm_cb(self):
        #prompt user if current document has not been saved
        if not self.check_current_document():
            return

        dialog = QFileDialog(self, 'Open State Machine', '~')
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setViewMode(QFileDialog.List)
        if dialog.exec_():
            filenames = dialog.selectedFiles()
            filename = str(filenames[0])

            #Set this a the new model
            self._set_model(gm.GraphModel.load(filename))
            self._reconnect_smach_states()

            #Reset state of GUI
            self.nothing_cb(None)
            #self.document = FSMDocument(filename, modified=False, real_filename=True)

    def run_sm_cb(self, checked):
        #TODO Disable all buttons.
        #TODO Reflect state of running graph.
        if self.graph_model.get_start_state() == None:
            QMessageBox.information(self, str(self.objectName()), 'No start state set.  Select a state and click on \'Start State\' to set a new start state.')
        else:
            try:
                self.run_state_machine(self.graph_model.create_state_machine())
            except RuntimeError, e:
                QMessageBox.information(self, str(self.objectName()), 'RuntimeError: ' + e.message)

    def stop_sm_cb(self):
        if self.graph_model.sm_thread.has_key('run_sm'):
            self.graph_model.sm_thread['run_sm'].preempt()
            self.graph_model.sm_thread['preempted'] = time.time()
    
    ##################
    # Behavior tools
    ##################
    def start_state_cb(self):
        if self.selected_node != None:
            try:
                self.graph_model.set_start_state(self.selected_node)
            except RuntimeError, e:
                QMessageBox.information(self, str(self.objectName()), 'RuntimeError: ' + e.message)

    def run_cb(self):
        if self.selected_tool == None:
            return
        try:
            tool_instance = self.tool_dict[self.selected_tool]['tool_obj']
            node = tool_instance.create_node(unique=False)
            singleton_sm = self.graph_model.create_singleton_statemachine(node)
            self.run_state_machine(singleton_sm)
        except RuntimeError, e:
            QMessageBox.information(self, str(self.objectName()), 'RuntimeError: ' + e.message)

    def add_cb(self):
        if self.selected_tool == None:
            return
        tool_instance = self.tool_dict[self.selected_tool]['tool_obj']
        if hasattr(tool_instance, 'set_child_node'):
            if self.selected_node == None:
                QMessageBox.information(self, str(self.objectName()), 'Need to have another node selected to create an instance of this node.')
                return
            else:
                smach_state = self.graph_model.get_smach_state(self.selected_node)
                tool_instance.set_child_node(smach_state)

        smach_node = tool_instance.create_node()
        self.graph_model.add_node(smach_node)
        if self.selected_node == None:
            self.node_cb(self.graph_model.node(smach_node.name))
        else:
            snode = self.graph_model.node(self.selected_node)
            if snode != None:
                self.node_cb(snode)
            else:
                self.nothing_cb(None)
                #self.selected_node = None

        self.tool_dict[self.selected_tool]['tool_obj'].refresh_connections_box()
        self.graph_view.refresh()
        self.graph_model.document.modified = True

    def reset_cb(self):
        if self.selected_tool == None:
            return
        tool_instance = self.tool_dict[self.selected_tool]['tool_obj']
        tool_instance.reset()

    def save_cb(self):
        tool_instance = self.tool_dict[self.selected_tool]['tool_obj']
        #old_smach_node = self.graph_model.get_smach_state()
        old_node_name = tool_instance.get_current_node_name()
        # create a node with new settings
        smach_node = tool_instance.create_node(unique=False)
        # 'delete' old smach node
        self.graph_model.replace_node(smach_node, old_node_name)
        #self.graph_model.set_smach_state(old_smach_node.get_name(), smach_node)

        # connection changes are made instantly (so don't worry about them)
        # only saving of internal node parameters must be implemented by client tools
        self.graph_model.document.modified = True

    def connection_changed(self, node_name, outcome_name, new_outcome):
        self.graph_model.connection_changed(node_name, outcome_name, new_outcome)
        self.graph_model.document.modified = True

    ##################
    # Graph tools
    ##################
    def disable_buttons(self):
        self.ui.run_button.setDisabled(True)
        self.ui.reset_button.setDisabled(True)
        self.ui.add_button.setDisabled(True)
        self.ui.save_button.setDisabled(True)

    def enable_buttons(self):
        self.ui.run_button.setDisabled(False)
        self.ui.reset_button.setDisabled(False)
        self.ui.add_button.setDisabled(False)
        self.ui.save_button.setDisabled(False)

    def deselect_tool_buttons(self):
        self.button_group_tab.setExclusive(False)
        button = self.button_group_tab.checkedButton()
        #print button
        if button != None:
            #print 'checked', button.isChecked(), button.isDown(), button.isCheckable(), button.text()
            button.setDown(False)
            button.setChecked(False)
            #print 'checked2', button.isChecked(), button.isDown()
        self.button_group_tab.setExclusive(True)

    def edit_mode(self):
        self.ui.add_button.hide()
        self.ui.save_button.show()

    def add_mode(self):
        self.ui.add_button.show()
        self.ui.save_button.hide()

    def empty_properties_box(self):
        self.empty_container(self.ui.properties_tab)
        self.empty_container(self.ui.connections_tab)

    def delete_cb(self):
        if self.selected_node != None:
            if self.selected_node != 'start':
                self.graph_model.delete_node(self.selected_node)
                self.set_selected_node(None)
                self.graph_view.refresh()
            else:
                print 'Can\'t delete start node!'

        #TODO rethink deleting of edges
        #if self.selected_edge != None:
        #    se = self.selected_edge
        #    self.set_selected_edge(None, None)
        #    self.graph_model.delete_edge(se)
        #    self.graph_view.refresh()
        self.graph_model.document.modified = True
        self.nothing_cb(None)

    def nothing_cb(self, pt):
        self.set_selected_node(None)
        self.set_selected_edge(None, None, None)
        self.empty_properties_box()
        self.add_mode()
        self.disable_buttons()
        self.deselect_tool_buttons()

    def node_cb(self, node):
        #print '================================= NODECB'
        self.set_selected_node(node.id)
        self.set_selected_edge(None, None, None)
        smach_state = self.graph_model.get_smach_state(node.id)

        #tool = self.tool_dict[smach_state.tool_name]['tool_obj']
        tool = self.tool_dict[smach_state.__class__]['tool_obj']
        tool.button.setChecked(True)

        #print '??????????'
        tool.activate_cb(smach_state.get_name())
        #print '??????????'

        #self.set_selected_tool(smach_state.tool_name)
        self.set_selected_tool(smach_state.__class__)

        self.edit_mode()
        self.enable_buttons()
        tool.node_selected(smach_state)

        if smach_state.is_runnable():
            self.ui.run_button.setDisabled(False)
        else:
            self.ui.run_button.setDisabled(True)
        #print '--------------------------------- NODECB'

    def edge_cb(self, edge):
        self.set_selected_edge(edge.node1.id, edge.node2.id, edge.label)
        self.set_selected_node(None)
        self.disable_buttons()

    #Handler for double clicking on a node, descending a level
    def dclick_cb(self, node):
        snode = self.graph_model.get_smach_state(node.id)
        if gm.is_container(snode):
            self.fsm_stack.append(FSMStackElement(self.graph_model, self.graph_view, snode))
            self._set_model(snode.get_child())
            self._reconnect_smach_states()
            self.nothing_cb(None)

    #Handler for double clicing on circle, ascending a level
    def dclick_container_cb(self, fsm_stack_element):

        #Store current model
        last_fsm_el = self.fsm_stack[-1]
        #last_fsm_el.node.set_child(self.graph_model)

        ######
        #recreate the old node with this new model as a child
        #each node need a function that lets you recreate it
        # what to call this? recreate? update?
        #       input: old node
        #       output: new node
        new_smach_node = last_fsm_el.node.recreate(self.graph_model)
        
        #replace old node in the graph, reserving links which exist
        # replace_node (fix it so that it works with new nodes of the same name)
        # restore_consistency
        last_fsm_el.model.replace_node(new_smach_node, last_fsm_el.node.get_name())

        #Shorten the stack to the element selected
        self.fsm_stack = self.fsm_stack[:self.fsm_stack.index(fsm_stack_element)]

        #Load the element we're given
        self._set_model(fsm_stack_element.model, view=fsm_stack_element.view)
        self._reconnect_smach_states()
        self.nothing_cb(None)
        #self.document = fsm_stack_element.document

        

        #Look up where the current level came from and save state
        #find the smach node that we expanded
        #give it back the graph model

        #node is container              (in memory)
        #node is a wrapper of some sort (in memory, but has constraints)
        #   containers need to be picklable, if has more than one nodes inside...
        #   maybe it would be a good idea to make subfolders for things with containers so that loading them
        #   would load subcomponents to

        #node is loaded state machine   (has file on disk)

        #Constraint: we can't save graph model objects with pickling, has to occur through 'load' and 'save'


    #####################################################################
    # Drawing
    #####################################################################
    def setup(self):
        graph._ctx = self.context
        self._set_model(gm.GraphModel())

    def _set_model(self, model, view=None):
        self.graph_model = model
        if view == None:
            self.graph_view = GraphView(self.context, self.graph_model)
            self.graph_view.setup()
        else:
            self.graph_view = view

        self.graph_model.gve.events.click = self.node_cb
        self.graph_model.gve.events.click_edge = self.edge_cb
        self.graph_model.gve.events.click_nothing = self.nothing_cb
        self.graph_model.gve.events.dclick = self.dclick_cb
        self.graph_view.fsm_dclick_cb = self.dclick_container_cb
        #self.graph_model.gve.events.right_drag = self.graph_view.drag_background_cb

    def draw(self):
        w = self.ui.graphicsSuperView.viewport().width()
        h = self.ui.graphicsSuperView.viewport().height()
        n = self.graph_model.document.get_name()
        properties_dict = {'selected_edge': self.selected_edge,
                           'selected_node': self.selected_node,
                           'width': w,
                           'height': h,
                           'name': n, 
                           'fsm_stack': self.fsm_stack}
        self.graph_view.draw(properties_dict)


class GraphView:

    def __init__(self, context, graph_model):
        self.graph_model = graph_model
        g = self.graph_model.gve
        self.gve = g
        self.context = context 

        node_outlines = self.context.color(0.4, 0.4, 0.4, 1.)
        text_color = self.context.color(0.3, 0.3, 0.3, 1.)
        node_font_size = 11

        #Customizations
        g.styles.default.depth = True
        g.styles.default.background = self.context.color(1., 1., 1., 1.)
        g.styles.default.stroke = node_outlines
        g.styles.default.text = text_color
        g.styles.default.fontsize = node_font_size
        g.styles.root.text = self.context.color(255/255., 153/255., 51/255., 1.)

        g.styles.important.fontsize = node_font_size
        g.styles.important.text = text_color
        g.styles.important.stroke = node_outlines

        g.styles.marked.fontsize = node_font_size
        g.styles.marked.text = text_color
        g.styles.marked.stroke = node_outlines
        #g.styles.default.fontsize = 12
        #g.styles.light.fontsize = 12
        #g.styles.back.fontsize = 12
        #g.styles.marked.fontsize = 12

        #g.styles.dark.fontsize = 12
        #g.styles.highlight.fontsize = 12
        #g.styles.root.fontsize = 12


        self.refresh = self.gve.layout.refresh
        selected_style = g.styles.create('selected')
        normal_style   = g.styles.create('normal')
        normal_edge_style   = g.styles.create('normal_edge')
        selected_edge_style = g.styles.create('selected_edge')
        graph_circle = g.styles.create('graph_circle')
        container = g.styles.create('container')
        container_selected = g.styles.create('container_selected')

        copy_style(g.styles.important, selected_style)
        copy_style(g.styles.default, normal_style)
        copy_style(g.styles.default, normal_edge_style)
        copy_style(g.styles.default, selected_edge_style)
        copy_style(g.styles.default, graph_circle)
        copy_style(g.styles.default, container)
        copy_style(g.styles.default, container_selected)

        graph_circle.fill = self.context.color(.96, .96, .96, .96)
        graph_circle.stroke = self.context.color(.8, .8, .8, 1.)
        graph_circle.strokewidth = 3
        graph_circle.fontsize = 24
        graph_circle.textwidth = 800
        graph_circle.text = self.context.color(.5, .5, .5, 1.)

        container.fill          = self.context.color(255./255, 204./255, 102./255., .4)
        container.node = g.styles.important.node

        container_selected.fill = self.context.color(255./255, 204./255, 102./255., 1.)
        container_selected.node = g.styles.important.node

        selected_style.text = text_color
        selected_edge_style.stroke = self.context.color(0.80, 0.00, 0.00, 0.75)
        selected_edge_style.strokewidth = 1.0

        self.radii_increment = 150
        self.fsm_start_color = 1.
        self.fsm_end_color = .96
        self.fsm_stroke_color = .85
        self.fsm_current_context_node = None
        self.fsm_dclick_cb = None

        self.right_clicked = None
        self.dx = 0.
        self.dy = 0.
        self.tx = 0.
        self.ty = 0.
        #g.node('start').style = 'marked'

    def set_node_style(self, node_name, style):
        self.gve.node(node_name).style = style
        self.gve.layout.refresh()

    def get_node_style(self, node_name):
        return self.gve.node(node_name).style
    
    #def drag_background_cb(self, s, e):
    #    #print start_click.x, start_click.y
    #    #print curr_pos.x, curr_pos.y

    #    #transform.scale(self.zoom, self.zoom)
    #    self.dx = e.x - s.x
    #    self.dy = e.y - s.y
    #    #print dx, dy
    #    #transform = QTransform()
    #    ##transform.scale(abs(dx), abs(dy))
    #    #transform.translate(dx, dy)
    #    #self.graphicsView.superView.setTransform(transform)

    def setup(self):
        self.context.speed(30.)
        self.context.size(700, 700)
        self.times = {}
        self.times['draw'] = 0.
        self.times['check'] = 0.
        self.times['iter'] = 0

    def _background_drag(self):
        mouse_pose = self.context._ns['MOUSEX'], self.context._ns['MOUSEY']

        if self.context._ns['rightdown']:
            if not self.right_clicked:
                self.right_clicked = mouse_pose
            else:
                self.tx = mouse_pose[0] - self.right_clicked[0]
                self.ty = mouse_pose[1] - self.right_clicked[1]
        else:
            #Commit transform
            self.right_clicked = None
            self.dx += self.tx
            self.dy += self.ty
            self.ty = 0.
            self.tx = 0.


        #if self._ctx._ns["rightdown"]:
        #    #Make sure we're not in any nodes
        #    in_nodes = False
        #    for n in self.graph.nodes:
        #        if self.mouse in n:
        #            in_nodes = True
        #            break

        #    #Set pose first time
        #    if not in_nodes and not self.right_clicked:
        #        self.right_clicked = self.mouse
        #    else:
        #        self.right_drag(self.right_clicked, self.mouse)

        #else:
        #    self.right_clicked = None

    def draw(self, properties_dict):
        START_TIME = time.time()
        self.context.size(properties_dict['width'], properties_dict['height'])
        cx = self.context
        g  = self.gve

        debug = False
        if debug:
            print 'dr',

        for n in g.nodes:
            if properties_dict['selected_node'] == n.id:
                self.set_node_style(n.id, 'selected')
            else:
                self.set_node_style(n.id, 'normal')

            if self.graph_model.get_start_state() == n.id:
                if self.get_node_style(n.id) == 'selected':
                    self.set_node_style(n.id, 'important')
                else:
                    self.set_node_style(n.id, 'marked')

            if hasattr(self.graph_model.get_smach_state(n.id), 'get_child'):
                if self.get_node_style(n.id) == 'selected':
                    self.set_node_style(n.id, 'container_selected')
                else:
                    self.set_node_style(n.id, 'container')

        if debug:
            print 'aw',
        self.set_node_style(tu.InfoStateBase.GLOBAL_NAME, 'root')

        draw_func = None
        #if properties_dict['selected_edge'] != None:

        def draw_selected():
            if properties_dict['selected_edge'] == None:
                return
            cx = self.context
            g  = self.gve
            #edge = self.selected_edge 
            edge = properties_dict['selected_edge']
            x0, y0 = edge.node1.x, edge.node1.y
            x1, y1 = edge.node2.x, edge.node2.y
            coordinates = lambda x, y, d, a: (x+math.cos(math.radians(a))*d, y+math.sin(math.radians(a))*d)

            # Find the edge's angle based on node1 and node2 position.
            a = math.degrees(math.atan2(y1-y0, x1-x0))
            # draw line from node's edge instead of it's center.
            r = edge.node2.r
            d = math.sqrt(pow(x1-x0, 2) + pow(y1-y0, 2))
            x00, y00 = coordinates(x0, y0, r+1, a)
            x01, y01 = coordinates(x0, y0, d-r-1, a)

            # draw
            p1 = [x00, y00]
            p2 = [x01, y01]
            cx.fill()
            cx.strokewidth(1.0)
            cx.stroke(1., 153./255., 0, .75)
            cx.beginpath(p1[0], p1[1])
            cx.lineto(p2[0], p2[1])
            path = cx.endpath(False)
            gs.edge_arrow(g.styles[edge.node1.style], path, edge, radius=10)
            cx.drawpath(path)

        def draw_fsm_circles():
            g = self.gve

            #figure out where centroids should be
            coords = []
            [coords.append([n.x, n.y]) for n in g.nodes]
            coords = np.matrix(coords).T
            centroid = np.median(coords, 1)

            #calculate where radii should be
            radius = np.max(np.power(np.sum(np.power((coords - centroid), 2), 0), .5)) + gm.GraphModel.NODE_RADIUS*2
            radius = max(radius, 200.)
            container_style = g.styles.graph_circle
            container_stroke = container_style.stroke
            
            ##
            #Draw fsm_stack
            stack = copy.copy(properties_dict['fsm_stack'])
            #stack.reverse()
            #smallest_radii = radius
            largest_radii = radius + len(stack) * self.radii_increment
            color = self.fsm_start_color
            if len(stack) > 0:
                color_incre = (self.fsm_start_color - self.fsm_end_color) / len(stack)

            #draw stack
            for el in stack:
                #smallest_radii = smallest_radii + self.radii_increment
                name = el.model.document.get_name()#el.document.get_name()

                #Draw node
                stack_node = graph.node(g, radius = largest_radii, id = name)
                stack_node.x, stack_node.y = centroid[0,0], centroid[1,0]
                el.graph_node = stack_node
                container_style.fill = self.context.color(color, color, color, 1.)
                container_style.stroke = self.context.color(self.fsm_stroke_color, self.fsm_stroke_color, 1.)
                gs.node(container_style, stack_node, g.alpha)

                #Draw label
                node_label_node_ = graph.node(g, radius = largest_radii, id = name)
                node_label_node_.x, node_label_node_.y = centroid[0,0], centroid[1,0] - largest_radii
                gs.node_label(container_style, node_label_node_, g.alpha)

                color -= color_incre
                largest_radii -= self.radii_increment

            ##
            #Draw node

            #Draw node circle
            graph_name_node = graph.node(g, radius=radius, id = properties_dict['name'])
            graph_name_node.x, graph_name_node.y = centroid[0,0], centroid[1,0]
            self.fsm_current_context_node = graph_name_node
            container_style.fill = self.context.color(self.fsm_end_color, self.fsm_end_color, self.fsm_end_color, 1.)
            container_style.stroke = container_stroke
            gs.node(container_style, graph_name_node, g.alpha)

            #draw node label
            node_label_node = graph.node(g, radius=radius, id = properties_dict['name'])
            node_label_node.x, node_label_node.y = centroid[0,0], centroid[1,0] - radius
            gs.node_label(container_style, node_label_node, g.alpha)


        def detect_fsm_click():
            def in_node(x, y, n):
                return (abs(x - n.x) < n.r) and (abs(y - n.y) < n.r)

            mousex_g = self.context._ns['MOUSEX'] - self.gve.x
            mousey_g = self.context._ns['MOUSEY'] - self.gve.y
            if self.context._ns['mousedoubleclick'] and len(properties_dict['fsm_stack']) > 0:
                if not in_node(mousex_g, mousey_g, self.fsm_current_context_node):
                    stack = copy.copy(properties_dict['fsm_stack'])
                    stack.reverse()
                    selected_el = None
                    for el in stack:
                        if in_node(mousex_g, mousey_g, el.graph_node):
                        #if p in el.graph_node:
                            selected_el = el
                            break

                    #selected something so load it
                    if selected_el != None and self.fsm_dclick_cb != None:
                        self.fsm_dclick_cb(selected_el)

        def final_func():
            draw_selected()
            detect_fsm_click()

        CHECK_TIME = time.time()
        self._background_drag()
        self.context._ns['MOUSEX'] -= self.dx+self.tx
        self.context._ns['MOUSEY'] -= self.dy+self.ty

        g.draw(dx=self.dx+self.tx, dy=self.dy+self.ty, directed=True, traffic=False, user_draw_start=draw_fsm_circles, user_draw_final=final_func)

        DRAW_TIME = time.time()

        total_draw = DRAW_TIME - CHECK_TIME
        total_check = CHECK_TIME - START_TIME
        self.times['draw'] += total_draw
        self.times['check'] +- total_check
        self.times['iter'] += 1
        #print 'draw', (1000.* self.times['draw'] / self.times['iter']), 'check', (1000.* self.times['check'] / self.times['iter'])

        if debug:
            print 'ing'


app = QtGui.QApplication(sys.argv)
rc = RCommanderWindow()
rc.add_tools([
              ['Manipulation', tt.TuckTool(rc)],
              ['Manipulation', lmt.LinearMoveTool(rc)],
              ['Manipulation', mat.SafeMoveArmTool(rc)],
              ['Manipulation', mt.JointSequenceTool(rc)],
              ['Manipulation', gt.GripperTool(rc)],
              ['Perception', ptl.Point3DTool(rc)],
              ['Perception', get.GripperEventTool(rc)],
              ['Navigation and Misc', nt.NavigateTool(rc)], 
              ['Navigation and Misc', spt.SpineTool(rc)],
              ['Navigation and Misc', smt.StateMachineTool(rc)],
              ['Navigation and Misc', st.SleepTool(rc)]
              #['Navigation and Misc', skt.SpeakTool(rc)]
              ])
rc.show()
sys.exit(app.exec_())






























































#class ThreadRunSM(threading.Thread):
#
#    def __init__(self, sm_name, sm):
#        threading.Thread.__init__(self)    
#        self.sm = sm
#        self.sm_name = sm_name
#        self.outcome = None
#        self.intro_server = None
#        self.exception = None
#
#    def run(self):
#        rospy.loginfo('ThreadRunSM started with %s' % self.sm_name)
#        try:
#            self.intro_server = smach_ros.IntrospectionServer(self.sm_name, self.sm, '/' + self.sm_name)
#            self.intro_server.start()
#            self.outcome = self.sm.execute()
#        except smach.InvalidTransitionError, e:
#            self.exception = e
#        except UserStoppedException, e:
#            self.exception = e
#            rospy.loginfo('ThreadRunSM: execution stopped')
#        rospy.loginfo('ThreadRunSM finished')
#
#    def except_stop(self):
#        while self.isAlive():
#            self._raise_exception()
#            time.sleep(.1)
#
#    def _raise_exception(self):
#        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(self.ident), ctypes.py_object(UserStoppedException))
#        if res == 0:
#            raise ValueError("Invalid thread ID")
#        elif res != 1:
#            # "if it returns a number greater than one, you're in trouble,
#            # and you should call it again with exc=NULL to revert the effect"
#            ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, 0)
#            raise SystemError("PyThreadState_SetAsyncExc failed")

###
## Checks for errors and redraw status bar if needed
###
#class ThreadRunSMMonitor(threading.Thread):
#
#    def __init__(self, sm_thread, parent_window):
#        threading.Thread.__init__(self)    
#        self.sm_thread = sm_thread
#        self.parent_window = parent_window
#
#    def run(self):
#        print 'ThreadRunSMMonitor: started'
#        r = rospy.Rate(10)
#        while not rospy.is_shutdown():
#
#            if self.sm_thread.exception != None:
#                m = self.sm_thread.exception.message
#                self.parent_window.statusBar().showMessage('InvalidTransitionError: %s' % m, 15000)
#                return
#
#            if self.sm_thread.outcome != None:
#                self.parent_window.statusBar().showMessage('Finished with outcome: %s' % self.sm_thread.outcome, 15000)
#                return
#
#            if not self.sm_thread.isAlive():
#                self.parent_window.statusBar().showMessage('Error: SM thread unexpectedly died.', 15000)
#                return
#
#            r.sleep()
#        print 'ThreadRunSMMonitor: returned'


#class GraphModel:
#
#    #Information about graph connectivity
#    EDGES_FILE = 'edges.graph'
#
#    #Misc information about graph itself
#    NODES_FILE = 'nodes.graph'
#
#    def __init__(self):
#        self.gve = graph.create(depth=True)
#        self.smach_states = {}
#        self.start_state = None
#        self.node = self.gve.node
#        self.edge = self.gve.edge
#
#        self.add_outcome(tu.InfoStateBase.GLOBAL_NAME)
#
#    def get_start_state(self):
#        return self.start_state
#
#    def set_start_state(self, state):
#        if state == tu.InfoStateBase.GLOBAL_NAME or issubclass(self.smach_states[state].__class__, tu.InfoStateBase):
#            raise RuntimeError("Can\'t make info states start states")
#        self.start_state = state
#
#    @staticmethod
#    def load(name):
#        state_pkl_names = glob.glob(pt.join(name, '*.state'))
#
#        gm = GraphModel()
#        gm.smach_states = {}
#
#        #Load individual states
#        for fname in state_pkl_names:
#            sname = pt.splitext(pt.split(fname)[1])[0]
#            pickle_file = open(fname, 'r')
#            rospy.loginfo('Loading state %s' % sname)
#            gm.smach_states[sname] = pk.load(pickle_file)
#            pickle_file.close()
#
#        #Reconstruct graph
#        graph_name = pt.join(name, GraphModel.EDGES_FILE)
#        pickle_file = open(graph_name, 'r')
#        edges = pk.load(pickle_file)
#        pickle_file.close()
#        for node1, node2, n1_outcome in edges:
#            #print node1, node2, n1_outcome
#            gm.gve.add_edge(node1, node2)
#            eobject = gm.edge(node1, node2)
#            eobject.outcome = n1_outcome
#
#        #Get meta info
#        nodes_fn = pt.join(name, GraphModel.NODES_FILE)
#        pickle_file = open(nodes_fn, 'r')
#        info = pk.load(pickle_file)
#        gm.start_state = info['start_state']
#        return gm
#
#    def save(self, name):
#        if not pt.exists(name):
#            os.mkdir(name)
#
#        #Save each state
#        for state_name in self.smach_states.keys():
#            state_fname = pt.join(name, state_name) + '.state'
#            pickle_file = open(state_fname, 'w')
#            pk.dump(self.smach_states[state_name], pickle_file)
#            pickle_file.close()
#
#        #Save connections
#        edge_list = []
#        for e in self.gve.edges:
#            edge_list.append([e.node1.id, e.node2.id, e.outcome])
#
#        edge_fn = pt.join(name, GraphModel.EDGES_FILE)
#        pickle_file = open(edge_fn, 'w')
#        pk.dump(edge_list, pickle_file)
#        pickle_file.close()
#
#        nodes_fn = pt.join(name, GraphModel.NODES_FILE)
#        pickle_file = open(nodes_fn, 'w')
#        pk.dump({'start_state': self.start_state}, pickle_file)
#        pickle_file.close()
#
#    def create_state_machine(self):
#        #print '>>>>>>>>>>>>>> create_state_machine'
#        sm = smach.StateMachine(outcomes=self.outcomes())
#        for global_node_name in self.global_nodes(None):
#            global_node = self.smach_states[global_node_name]
#            global_variable_name = global_node.get_name()
#            value = global_node.get_info()
#            exec_str = "sm.userdata.%s = value" % global_variable_name
#            print 'executing', exec_str
#            exec exec_str
#
#        with sm:
#            for node_name in self.nonoutcomes():
#                node = self.smach_states[node_name]
#                if issubclass(node.__class__, tu.InfoStateBase):
#                    continue
#
#                transitions = {}
#                print node_name
#                for e in self.gve.node(node_name).edges:
#                    if e.node1.id == node_name:
#                        transitions[e.outcome] = e.node2.id
#                        print e.node1.id, e.outcome, e.node2.id
#
#                remapping = {}
#                for input_key in node.get_registered_input_keys():
#                    remapping[input_key] = node.source_for(input_key)
#                print '>> node_name', node_name, 'transitions', transitions, 'remapping', remapping
#                smach.StateMachine.add(node_name, node, transitions=transitions, remapping=remapping)
#
#        if self.start_state == None:
#            raise RuntimeError('No start state set.')
#        #print 'create_state_machine start state is', self.start_state
#        sm.set_initial_state([self.start_state])
#        #print '<<<<<<<<<<<<<<'
#        return sm
#
#    def nonoutcomes(self):
#        noc = []
#        for node_name in self.smach_states.keys():
#            if self.smach_states[node_name].__class__ != ot.EmptyState:
#                noc.append(node_name)
#        return noc
#
#    #@return a list of node names and outcomes
#    #        e.g. [[edge_name, node_name], ...]
#    def current_children_of(self, node_name):
#        ret_list = []
#        for edge in self.gve.node(node_name).edges:
#            if edge.node1.id != node_name:
#                continue
#            ret_list.append([edge.outcome, edge.node2.id])
#        return ret_list
#
#    def outcomes(self):
#        #all empty states are outcomes
#        oc = []
#        for node_name in self.smach_states.keys():
#            if self.smach_states[node_name].__class__ == ot.EmptyState:
#                oc.append(node_name)
#        #print 'outcomes', oc
#        return oc
#
#    def pop_smach_state(self, node_name):
#        return self.smach_states.pop(node_name)
#
#    def get_smach_state(self, node_name):
#        #print self.smach_states.keys()
#        return self.smach_states[node_name]
#
#    def set_smach_state(self, node_name, state):
#        self.smach_states[node_name] = state
#
#    def replace_node(self, new_node, old_node_name):
#        self.smach_states.pop(old_node_name)
#        self.smach_states[new_node.get_name()] = new_node
#        new_node_name = new_node.get_name()
#
#        if new_node_name != old_node_name:
#            self.gve.add_node(new_node_name)
#            for e in self.gve.node(old_node_name).edges:
#                outcome = e.outcome
#                self.gve.remove_edge(e.node1.id, e.node2.id)
#                print 'removing edge between', e.node1.id, e.node2.id
#                if e.node1.id == old_node_name:
#                    self.gve.add_edge(new_node_name, e.node2.id)
#                    self.gve.edge(new_node_name, e.node2.id).outcome = outcome
#                    print 'adding edge between', new_node_name, e.node2.id
#                    #edges.append([new_node_name, e.node2.id])
#                else:
#                    self.gve.add_edge(e.node1.id, new_node_name)
#                    self.gve.edge(e.node1.id, new_node_name).outcome = outcome
#                    #edges.append([e.node1.id, new_node_name])
#                    print 'adding edge between', e.node1.id, new_node_name
#
#            self.gve.remove_node(old_node_name)
#
#    #def _outcome_name(self, node_name, outcome):
#    #    return node_name + '_' + outcome
#
#    def connectable_nodes(self, node_name, outcome):
#        #can't connect to
#        #  temporary nodes already connected whose name is not current outcome
#        allowed_nodes = []
#        #outcome_name = self._outcome_name(node_name, outcome)
#        #allowed_nodes.append(outcome_name)
#        for k in self.smach_states.keys():
#            #If it's a temporary node and does not have the name of this outcome
#            #if not self.is_modifiable(k) and k != outcome:
#            if (not self.is_modifiable(k)) and (not self._is_type(k, outcome)):
#                continue
#            #ignore our own name
#            if node_name == k:
#                continue
#            #ignore special global node
#            if k == tu.InfoStateBase.GLOBAL_NAME:
#                continue
#
#            allowed_nodes.append(k)
#
#        if node_name == None:
#            allowed_nodes.append(self._create_outcome_name(outcome))
#            allowed_nodes = list(set(allowed_nodes))
#
#        return allowed_nodes
#
#    ##
#    # @return a list of nodes that are of subclass InfoStateBase
#    def global_nodes(self, class_filter):
#        allowed_nodes = []
#        for k in self.smach_states.keys():
#            state = self.smach_states[k]
#            if issubclass(state.__class__, tu.InfoStateBase):
#                if class_filter != None:
#                    if state.__class__ == class_filter:
#                        allowed_nodes.append(k)
#                else:
#                    allowed_nodes.append(k)
#        allowed_nodes.sort()
#        return allowed_nodes
#
#    def _create_outcome_name(self, outcome):
#        idx = 0
#        name = "%s%d" % (outcome, idx)
#        while self.smach_states.has_key(name):
#            idx = idx + 1
#            name = "%s%d" % (outcome, idx)
#        return name
#
#    def _is_type(self, state_name, outcome):
#        r = state_name.find(outcome)
#        if r < 0:
#            return False
#        else:
#            return True
#
#    def add_node(self, smach_node):
#        if self.smach_states.has_key(smach_node.name):
#            raise RuntimeError('Already has node of the same name.  This case should not happen.')
#
#        #Link this node to all its outcomes
#        self.gve.add_node(smach_node.name)
#        self.smach_states[smach_node.name] = smach_node
#        #print 'adding node', smach_node.name, 'with outcomes', smach_node.get_registered_outcomes()
#        for outcome in smach_node.get_registered_outcomes():
#            #outcome_name = self._outcome_name(smach_node.name, outcome)
#            outcome_name = self._create_outcome_name(outcome)
#            #if not self.smach_states.has_key(outcome):
#            self.smach_states[outcome_name] = ot.EmptyState(outcome_name, temporary=True)
#            self.gve.add_node(outcome_name)
#            #self.gve.add_edge(smach_node.name, outcome)
#            self._add_edge(smach_node.name, outcome_name, outcome)
#
#    def add_outcome(self, outcome_name):
#        self.gve.add_node(outcome_name)
#        self.smach_states[outcome_name] = ot.EmptyState(outcome_name, False)
#
#    def delete_node(self, node_name):
#        node_obj = self.gve.node(node_name)
#        children_edges = []
#        parent_edges = []
#        for cn in node_obj.links:
#            edge = self.gve.edge(node_name, cn.id)
#            if (edge.node1.id == node_name) and (edge.node2.id == node_name):
#                raise Exception('Self link detected on node %s! This isn\'t supposed to happen.' % node_name)
#            if edge.node1.id == node_name:
#                children_edges.append(edge)
#            elif edge.node2.id == node_name:
#                parent_edges.append(edge)
#
#        #Remove placeholder children nodes
#        filtered_children_edges = []
#        for e in children_edges:
#            # If the connected node is not modifiable (i.e. a temporary added
#            # node) and it doesn't have any other parents.
#            if not self.is_modifiable(e.node2.id) and len(e.node2.edges) <= 1:
#                self.gve.remove_edge(node_name, e.node2.id)
#                self.gve.remove_node(e.node2.id)
#                self.smach_states.pop(e.node2.id)
#            else:
#                filtered_children_edges.append(e)
#
#        #If we have one or more than one parent
#        if len(parent_edges) >= 1:
#            parent_node_id = parent_edges[0].node1.id
#            parent_node = self.gve.node(parent_node_id)
#            parents_children = {}
#
#            for parent_outcome_name, sibling_node_name in self.current_children_of(parent_node_id):
#                parents_children[parent_outcome_name] = sibling_node_name
#
#            for edge in filtered_children_edges:
#                node_outcome_name = edge.outcome
#                parent_outcome_node = parents_children[node_outcome_name]
#
#                #if parent has a similar outcome connected to a temporary node
#                if parents_children.has_key(node_outcome_name):
#                    self.gve.remove_edge(parent_node_id, parent_outcome_node)
#                    #If parent outcome is connected to a temporary node
#                    if not self.is_modifiable(parent_outcome_node):
#                        #connect this child node to parent
#                        self.gve.add_edge(parent_node_id, node_outcome_name)
#                        e = self.gve.edge(parent_node_id, node_outcome_name)
#                        e.outcome = node_outcome_name
#                    #delete parent's temporary node if it is now unconnected
#                    if len(self.gve.node(parent_outcome_node).edges) <= 1:
#                        self.gve.remove_node(parent_outcome_node)
#                        self.smach_states.pop(parent_outcome_node)
#
#                #remove this edge
#                self.gve.remove_edge(edge.node1.id, edge.node2.id)
#
#        #If no parents
#        elif len(parent_edges) == 0:
#            #just remove children edges
#            for e in filtered_children_edges:
#                self.gve.remove_edge(node_name, e.node2.id)
#
#        #Remove edge from parents, and restore consistency for parent nodes
#        for parent_edge in parent_edges:
#            self.gve.remove_edge(parent_edge.node1.id, parent_edge.node2.id)
#            self.restore_node_consistency(parent_edge.node1.id)
#
#        self.gve.remove_node(node_name)
#        self.smach_states.pop(node_name)
#
#    def restore_node_consistency(self, node_name):
#        # For each registered outcome, make sure there exists an edge.  If no
#        # edge exists, create it.
#        #print 'restoring consistency of node', node_name
#
#        clist = self.current_children_of(node_name)
#        cdict = {}
#        #print 'outcomes that we have links for'
#        for outcome_name, nn in clist:
#            cdict[outcome_name] = nn
#            #print outcome_name, nn
#
#        #print self.smach_states[node_name].__class__
#        #print 'outcomes that we need', self.smach_states[node_name].get_registered_outcomes()
#
#        for outcome in self.smach_states[node_name].get_registered_outcomes():
#            if not cdict.has_key(outcome):
#                #print 'outcome', outcome, 'is missing. restoring connection'
#                new_outcome_name = self._create_outcome_name(outcome)
#                self._add_temporary_outcome(new_outcome_name)
#                self._add_edge(node_name, new_outcome_name, outcome)
#
#    def _add_temporary_outcome(self, outcome):
#        self.smach_states[outcome] = ot.EmptyState(outcome, temporary=True)
#        self.gve.add_node(outcome)
#
#    def delete_node_old(self, node_name):
#        #temporary nodes are only removable when the state transitions are linked to something else
#        if not self.is_modifiable(node_name):
#            return 
#
#        #Find parents and children
#        node_obj = self.gve.node(node_name)
#        children_edges = []
#        parent_edges = []
#        for cn in node_obj.links:
#            edge = self.gve.edge(node_name, cn.id)
#            if (edge.node1.id == node_name) and (edge.node2.id == node_name):
#                raise Exception('Self link detected on node %s! This isn\'t supposed to happen.' % node_name)
#            if edge.node1.id == node_name:
#                children_edges.append(edge)
#            elif edge.node2.id == node_name:
#                parent_edges.append(edge)
#
#        #Remove placeholder children nodes
#        filtered_children_edges = []
#        for e in children_edges:
#            if not self.is_modifiable(e.node2.id) and len(e.node2.edges) <= 1:
#                self.gve.remove_edge(node_name, e.node2.id)
#                self.gve.remove_node(e.node2.id)
#                self.smach_states.pop(e.node2.id)
#            else:
#                filtered_children_edges.append(e)
#
#        new_selected_node = None
#        #If we have one or more than one parent
#        if len(parent_edges) >= 1:
#            #Point edges on children to first parent
#            parent_node_id = parent_edges[0].node1.id
#            for e in filtered_children_edges:
#                self.gve.remove_edge(node_name, e.node2.id)
#                self.gve.add_edge(parent_node_id, e.node2.id)
#            new_selected_node = parent_node_id
#
#            #On each one of the parent, check to see if we are the terminal state
#            for e in parent_edges:
#                parent_id = e.node1.id
#                outcome_set = set(self.get_smach_state(parent_id).get_registered_outcomes())
#                if e.outcome in outcome_set:
#                    self.connection_changed(parent_id, e.outcome, e.outcome)
#                    #jjself.smach_states[e.outcome] = ot.EmptyState(e.outcome, temporary=True)
#                    #self.gve.add_node(e.outcome)
#                    #self._add_edge(parent_id, e.outcome, e.outcome)
#
#        #If no parents
#        elif len(parent_edges) == 0:
#            #just remove children edges
#            for e in filtered_children_edges:
#                self.gve.remove_edge(node_name, e.node2.id)
#
#            if len(filtered_children_edges) > 1:
#                new_selected_node = filtered_children_edges[0].node2.id
#            else:
#                if len(self.gve.nodes) > 0:
#                    new_selected_node = self.gve.nodes[0].id
#                else:
#                    new_selected_node = 'start'
#
#        self.gve.remove_node(node_name)
#        self.smach_states.pop(node_name)
#        return new_selected_node
#
#    def is_modifiable(self, node_name):
#        if (self.smach_states[node_name].__class__ == ot.EmptyState) and self.smach_states[node_name].temporary:
#            return False
#        else:
#            return True
#
#    def _add_edge(self, n1, n2, n1_outcome):
#        if not self.smach_states.has_key(n1) or not self.smach_states.has_key(n2):
#            raise RuntimeError('One of the specified nodes does not exist.  Can\'t add edge.')
#        if self.gve.edge(n1, n2) != None:
#            rospy.loginfo("Edge between %s and %s exists, ignoring connnection request" % (n1, n2))
#            return False
#
#        #Don't add edges to "temporary" nodes
#        if n1_outcome == None and self.is_modifiable(n2):
#            raise RuntimeError('Must specify outcome as goal node is not a temporary node.')
#
#        self.gve.add_edge(n1, n2)
#        self.gve.edge(n1, n2).outcome = n1_outcome
#        return True
#
#    def add_edge(self, n1, n2, n1_outcome):
#        if not self.is_modifiable(n1) or not self.is_modifiable(n2):
#            return False
#        else:
#            return self._add_edge(n1, n2, n1_outcome)
#
#    def delete_edge(self, edge):
#        if not self.is_modifiable(edge.node1.id) or not self.is_modifiable(edge.node2.id):
#            return False
#        else:
#            self.gve.remove_edge(edge.node1.id, edge.node2.id)
#            return True
#
#    def connection_changed(self, node_name, outcome_name, new_outcome):
#        #node is not valid or hasn't been created yet
#
#        if node_name == None:
#            return
#        if not self.smach_states.has_key(new_outcome):
#            raise RuntimeError('Doesn\'t have state: %s' % new_outcome)
#        #self.get_smach_state(node_name).outcome_choices[outcome_name] = new_outcome
#
#        #find the old edge
#        old_edge = None
#        for edge in self.gve.node(node_name).edges:
#            if edge.outcome == outcome_name and edge.node1.id == node_name:
#                if old_edge != None:
#                    raise RuntimeError('Two edges detected for one outcome named %s. %s -> %s and %s -> %s' % (outcome_name, old_edge.node1.id, old_edge.node2.id, edge.node1.id, edge.node2.id))
#                old_edge = edge
#
#        if old_edge.node2.id == new_outcome:
#            return
#
#        #print 'connection_changed', node_name, outcome_name, new_outcome
#        #remove the old connection
#        self.gve.remove_edge(node_name, old_edge.node2.id)
#        #remove the old node if it's temporary 
#        if not self.is_modifiable(old_edge.node2.id) and old_edge.node2.id != 'start':
#            #and not connected
#            if len(self.gve.node(old_edge.node2.id).edges) <= 0:
#                self.gve.remove_node(old_edge.node2.id)
#
#        #add new connection
#        if self.gve.node(new_outcome) == None:
#            print 'recreated node', new_outcome
#            self.smach_states[new_outcome] = ot.EmptyState(new_outcome, temporary=True)
#            self.gve.add_node(new_outcome)
#        self._add_edge(node_name, new_outcome, outcome_name)




    #def tuck_cb(self):
    #    #Load properties into properties box.
    #    self.add_node('tuck')
    #def navigate_cb(self):
    #    #Load properties into properties box.
    #    self.empty_properties_box()
    #    pbox = self.ui.behavior_properties_box
    #    formlayout = pbox.layout()

    #    xline = QLineEdit(pbox)
    #    formlayout.addRow("&x", xline)
    #    yline = QLineEdit(pbox)
    #    formlayout.addRow("&y", yline)
    #    tline = QLineEdit(pbox)
    #    formlayout.addRow("&theta", tline)
    #    pbox.update()

    #    # goal x
    #    # goal y
    #    # goal theta
    #    # frame

    #    # turn on markers
    #    # locat current location button
    #    #

    #    self.add_node('navigate')

    #def set_node_style(self, node_name, style):
    #    self.nb_graph.node(node_name).style = style
    #    self.nb_graph.layout.refresh()



   #def delete_node(self, node_name):
    #    #find parents and children
    #    node_obj = self.nb_graph.node(node_name)
    #    children_edges = []
    #    parent_edges = []
    #    for cn in node_obj.links:
    #        edge = self.nb_graph.edge(node_name, cn.id)
    #        if (edge.node1.id == node_name) and (edge.node2.id == node_name):
    #            raise Exception('Self link detected on node %s! This isn\'t supposed to happen.' % node_name)
    #        if edge.node1.id == node_name:
    #            children_edges.append(edge)
    #        elif edge.node2.id == node_name:
    #            parent_edges.append(edge)

    #    #If we have one or more than one parent
    #    if len(parent_edges) >= 1:
    #        #Point edges on children to first parent
    #        parent_node_id = parent_edges[0].node1.id
    #        for e in children_edges:
    #            self.nb_graph.remove_edge(node_name, e.node2.id)
    #            self.nb_graph.add_edge(parent_node_id, e.node2.id)
    #        if node_name == self.selected_node:
    #            self.set_selected_node(parent_node_id)

    #    #If no parents
    #    elif len(parent_edges) == 0:
    #        #just remove children edges
    #        for e in children_edges:
    #            self.nb_graph.remove_edge(node_name, e.node2.id)
    #        if node_name == self.selected_node:
    #            if len(children_edges) > 1:
    #                self.set_selected_node(children_edges[0].node2.id)
    #            else:
    #                if len(self.nb_graph.nodes) > 0:
    #                    self.set_selected_node(self.nb_graph.nodes[0].id)
    #                else:
    #                    self.set_selected_node('start')
    #    self.nb_graph.remove_node(node_name)
    #    self.nb_graph.layout.refresh()

    #def delete_edge(self, edge):
    #    self.nb_graph.remove_edge(edge.node1.id, edge.node2.id)
    #    self.nb_graph.layout.refresh()

    #def add_node(self, name):
    #    if self.selected_node != None:
    #        self.nb_graph.add_edge(self.selected_node, name)
    #        self.set_node_style(name, 'normal')
    #        self.nb_graph.layout.refresh()
    #        self.set_selected_node(name)
    #        return True
    #    else:
    #        return False



    #def draw(self):
    #    cx = self.context
    #    g  = self.nb_graph

    #    if self.selected_edge != None:
    #        def draw_selected():
    #            cx = self.context
    #            g  = self.nb_graph
    #            edge = self.selected_edge 
    #            x0, y0 = edge.node1.x, edge.node1.y
    #            x1, y1 = edge.node2.x, edge.node2.y
    #            coordinates = lambda x, y, d, a: (x+math.cos(math.radians(a))*d, y+math.sin(math.radians(a))*d)

    #            # Find the edge's angle based on node1 and node2 position.
    #            a = math.degrees(math.atan2(y1-y0, x1-x0))
    #            # draw line from node's edge instead of it's center.
    #            r = edge.node2.r
    #            d = math.sqrt(pow(x1-x0, 2) + pow(y1-y0, 2))
    #            x00, y00 = coordinates(x0, y0, r+1, a)
    #            x01, y01 = coordinates(x0, y0, d-r-1, a)

    #            # draw
    #            p1 = [x00, y00]
    #            p2 = [x01, y01]
    #            cx.fill()
    #            cx.strokewidth(1.0)
    #            cx.stroke(1., 153./255., 0, .75)
    #            cx.beginpath(p1[0], p1[1])
    #            cx.lineto(p2[0], p2[1])
    #            path = cx.endpath(False)
    #            gs.edge_arrow(g.styles[edge.node1.style], path, edge, radius=10)
    #            cx.drawpath(path)

    #        g.draw(directed=True, traffic=False, user_draw=draw_selected)
    #    else:
    #        g.draw(directed=True, traffic=False)










        #g.add_edge("roof"        , "house")
        #g.add_edge("garden"      , "house")
        #g.add_edge("room"        , "house")
        #g.add_edge("kitchen"     , "room")
        #g.add_edge("bedroom"     , "room")
        #g.add_edge("bathroom"    , "room")
        #g.add_edge("living room" , "room")
        #g.add_edge("sofa"        , "living room")
        #g.add_edge("table"       , "living room")
