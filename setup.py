from setuptools import setup, find_packages


setup(
    name='protoci',
    version='0.0.0',
    author='Continuum Analytics',
    author_email='psteinberg@continuum.io',
    url='http://github.com/ContinuumIO/protoci',
    packages=['protoci'],
    include_package_data=True,
    package_data={'protoci': ['protoci/data/*']},
    install_requires=['conda-build', 'networkx',
                      'PyYAML', 'requests',
                      'jinja2', 'psutil'],
    zip_safe=False,
    entry_points={
      'console_scripts': [
          'protoci-sequential-build = protoci.build2:sequential_build_main',
          'protoci-difference-build = protoci.build2:difference_build_main',
          'protoci-split-packages = protoci.split:make_package_tree_main',
          'protoci-submit = protoci.submit:submit_main'
          ],
    }
)
