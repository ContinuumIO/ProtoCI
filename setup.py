import os
from setuptools import setup, find_packages


def find_package_data():
    special_cases = os.path.join(os.path.dirname(__file__),
                                 'protoci',
                                 'special_cases')
    f = ['protoci/special_cases/*', 'protoci/special_cases']
    for parent, dirs, files in os.walk(special_cases):
        if files:
            for fil in files:
                f.append(os.path.join(parent, '*.*'))
                f.append(parent)
    print(f)
    return f


setup(
    name='protoci',
    version='0.0.32',
    author='Continuum Analytics',
    author_email='psteinberg@continuum.io',
    url='http://github.com/ContinuumIO/protoci',
    packages=['protoci'],
    include_package_data=True,
    package_data={'protoci': ['protoci/data/*',] + find_package_data()},
    install_requires=['networkx', 'setuptools',
                      'PyYAML', 'requests',
                      'jinja2', 'psutil',
                      'pytest','pycosat'],
    zip_safe=False,
    entry_points={
      'console_scripts': [
          'protoci-sequential-build = protoci.sequential_build:sequential_build_main',
          'protoci-difference-build = protoci.difference_build:difference_build_main',
          'protoci-split-packages = protoci.split:make_package_tree_main',
          'protoci-submit = protoci.submit:submit_main'
          ],
    }
)
