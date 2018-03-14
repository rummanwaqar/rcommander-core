from distutils.core import setup, Extension
 
module1 = Extension('nodebox_springlayout', 
        include_dirs=['/usr/lib/python2.7/dist-packages/numpy/core/include/numpy'],
        sources = ['nodebox_springlayout.c'])
 
setup (name = 'node_boxspringlayout',
        version = '1.0',
        description = 'calculates between node forces',
        ext_modules = [module1])

