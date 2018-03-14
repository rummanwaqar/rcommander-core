#import roslib; roslib.load_manifest('rcommander_core')
import sys
#import pdb
#pdb.set_trace()
import tool_utils as tu
import roslib.rospack
import inspect
import os

def load_plugins(robot_namespaces):
    """
    @return: list of static roswtf plugins, list of online
    roswtf plugins
    @rtype: [fn], [fn]
    """
    
    dependencies = roslib.rospack.rospack_depends_on_1('rcommander')
    plugin_classes = []
    print "DEPENDENCIES: " + str(dependencies)
    dependencies=['rcommander_plain']
    for pkg in dependencies:
        m_filename = roslib.manifest.manifest_file(pkg, True)
        manifest   = roslib.manifest.parse_file(m_filename)
        p_modules  = manifest.get_export('rcommander', 'plugin')
        p_tabs     = manifest.get_export('rcommander', 'tab')
        p_robots   = manifest.get_export('rcommander', 'robot')
        print str(p_modules) + " -- " + str(p_tabs) + " -- " + str(p_robots)
        if not p_modules:
            continue

        for p_module, p_tab, p_robot in zip(p_modules, p_tabs, p_robots):
            if not (p_robot in robot_namespaces):
                continue
            ## import the specified plugin module
            try:
                roslib.load_manifest(pkg)
                mod = __import__(p_module)
                for sub_mod in p_module.split('.')[1:]:
                    mod = getattr(mod, sub_mod)

                for cls in dir(mod):
                    cls_obj = getattr(mod, cls)
                    if inspect.isclass(cls_obj) and (tu.ToolBase in inspect.getmro(cls_obj)):
                        plugin_classes.append([p_tab, cls_obj])
            except Exception, e:
                print e.__class__, e
                print >> sys.stderr, "Unable to load plugin [%s] from package [%s]"% (p_module, pkg)
    return plugin_classes

if __name__ == '__main__':
    print load_plugins('rcommander')
