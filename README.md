# rcommander-core
Port of rcommander for indigo

## Run
`roslaunch rcommmander_plain rcommander_plain`

## Bugs
First try: `rosdep install rcommander_plain

If you get error: `ImportError: No module named nodebox_springlayout`

```
cd ~/catkin_ws/src/rcommander-core/nodebox_qt/src/graph
python setup.py install --user
```

If you get error: `ImportError: No module named PyQt4.QtGui`
```
sudo apt-get install python-qt4
```

If you get error: `ImportError: No module named QtOpenGL`
```
apt-get install python-qt4-gl
```
