#!/usr/bin/python
import roslib; roslib.load_manifest('rcommander_plain')
import rcommander.rcommander as rc
import rospy
import tf

class MyRobotClass:
    def __init__(self):
        self.some_resource = "hello"

rospy.init_node('rcommander_plain', anonymous=True)
robot = MyRobotClass()
tf    = tf.TransformListener()
rc.run_rcommander(['default', 'default_frame', 'myrobot'], robot, tf)
