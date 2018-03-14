# rcommander-core
Port of rcommander for indigo

## Run
`roslaunch rcommmander_plain rcommander_plain`

## Bugs
If you get error: `ImportError: No module named nodebox_springlayout`

```
cd ~/catkin_ws/src/rcommander-core/nodebox_qt/src/graph
python setup.py install --user
```
