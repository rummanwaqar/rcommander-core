import smach
import rospy
import rcommander.tool_utils as tu
from PyQt4.QtGui import *
from PyQt4.QtCore import *

class FooSmachState(smach.State):
    def __init__(self, total_counter):
        smach.State.__init__(self, outcomes=['outcome1','outcome2'])
        self.counter = 0
        self.total_counter = total_counter

    def execute(self, userdata):
        rospy.loginfo('Executing state FOO')
        if self.counter < self.total_counter:
            self.counter += 1
            return 'outcome1'
        else:
            return 'outcome2'
        
class FooState(tu.StateBase):

    def __init__(self, name, total_counter):
        tu.StateBase.__init__(self, name)
        self.total_counter = total_counter

    def get_smach_state(self):
        return FooSmachState(self.total_counter)
        
class FooTool(tu.ToolBase):

    def __init__(self, rcommander):
        tu.ToolBase.__init__(self, rcommander, 'foo', 'Foo', FooState)

    def fill_property_box(self, pbox):
        formlayout = pbox.layout()
        self.counter_box = QDoubleSpinBox(pbox)
        self.counter_box.setMinimum(0)
        self.counter_box.setMaximum(1000.)
        self.counter_box.setSingleStep(.2)
        self.counter_box.setValue(3.)
        formlayout.addRow("&N.Times", self.counter_box)

    def new_node(self, name=None):
        if name == None:
            nname = self.name + str(self.counter)
        else:
            nname = name
        return FooState(nname, self.counter_box.value())

    def set_node_properties(self, my_node):
        self.counter_box.setValue(my_node.total_counter)

    def reset(self):
        self.counter_box.setValue(3.)