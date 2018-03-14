import smach
import rospy
import rcommander.tool_utils as tu
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from smach import CBState
from std_msgs.msg import Empty
import smach_ros

@smach.cb_interface(input_keys=[], output_keys=[], outcomes=['finished','failed'])
def takeoff_cb( user_data):
    rospy.loginfo('Taking Off')
    takeoff_topic = rospy.Publisher('/drone/takeoff', Empty, queue_size=1)
    rospy.sleep(1)
    msg = Empty()
    result = takeoff_topic.publish(msg)
    if result == None:
        return 'finished'
    else:
        return 'failed'

        
class TakeoffState(tu.StateBase):

    def __init__(self, name):
        tu.StateBase.__init__(self, name)

    def get_smach_state(self):
        return CBState(takeoff_cb)
        
class TakeoffTool(tu.ToolBase):

    def __init__(self, rcommander):
        tu.ToolBase.__init__(self, rcommander, 'takeoff', 'Takeoff', TakeoffState)

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
        return TakeoffState(nname)

    def set_node_properties(self, my_node):
        self.counter_box.setValue(2.0)

    def reset(self):
        self.counter_box.setValue(3.)