#!/usr/bin/env python
from __future__ import print_function, division

import argparse
from collections import defaultdict
import datetime
import json
import psutil
import os
import shutil
import subprocess
import time
import networkx as nx
import sys


from conda_build.metadata import parse, MetaData

CONDA_BUILD_CACHE=os.environ.get("CONDA_BUILD_CACHE")

class PopenWrapper(object):
    # Small wrapper around subprocess.Popen to allow memory usage monitoring

    def __init__(self, *args, **kwargs):
        self.elapsed = None
        self.rss = None
        self.vms = None
        self.returncode=None
        self.disk = None

        #Process executed immediately
        self._execute(*args, **kwargs)

    def _execute(self, *args, **kwargs):
        # The polling interval (in seconds)
        time_int = kwargs.pop('time_int', 1)

        # Create a process of this (the parent) process
        parent = psutil.Process(os.getpid())
        initial_usage = psutil.disk_usage(sys.prefix).used

        # Using the convenience Popen class provided by psutil
        start_time = time.time()
        _popen = psutil.Popen(*args, **kwargs)
        try:
            while _popen.is_running():
                #We need to get all of the children of our process since our process spawns other processes
                # Collect all of the child processes

                try:
                    # We use the parent process to get mem usage of all spawned processes
                    child_pids = [_.memory_info() for _ in parent.children(recursive=True) if _.is_running()]
                    # Sum the memory usage of all the children together (2D columnwise sum)
                    rss, vms = [sum(_) for _ in zip(*child_pids)]

                    self.rss = max(rss, self.rss)
                    self.vms = max(vms, self.vms)

                    # Get disk usage
                    used_disk = initial_usage - psutil.disk_usage(sys.prefix).used
                    self.disk = max(used_disk, self.disk)

                except psutil.AccessDenied as e:
                    if _popen.status() == psutil.STATUS_ZOMBIE:
                        _popen.wait()

                time.sleep(time_int)
                self.elapsed = time.time() - start_time
                self.returncode = _popen.returncode
        except KeyboardInterrupt:
            _popen.kill()
            raise

    def __repr__(self):
        return str({'elapsed': self.elapsed,
                    'rss': self.rss,
                    'vms': self.vms,
                    'returncode': self.returncode})

def bytes2human(n):
    # http://code.activestate.com/recipes/578019
    # >>> bytes2human(10000)
    # '9.8K'
    # >>> bytes2human(100001221)
    # '95.4M'
    symbols = ('K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
    prefix = {}
    for i, s in enumerate(symbols):
        prefix[s] = 1 << (i + 1) * 10
    for s in reversed(symbols):
        if n >= prefix[s]:
            value = float(n) / prefix[s]
            return '%.1f%s' % (value, s)
    return "%sB" % n


def read_recipe(path):
    return MetaData(path)

def describe_meta(meta):
    """Return a dictionary that describes build info of meta.yaml"""

    # Things we care about and need fast access to:
    #   1. Package name and version
    #   2. Build requirements
    #   3. Build number
    #   4. Recipe directory
    d = {}

    d['build'] = meta.get_value('build/number', 0)
    d['depends'] = format_deps(meta.get_value('requirements/build'))
    d['version'] = meta.get_value('package/version')
    return d


def format_deps(deps):
    d = {}
    for x in deps:
        x = x.strip().split()
        if len(x) == 2:
            d[x[0]] = x[1]
        else:
            d[x[0]] = ''
    return d

def get_build_deps(recipe):
    return format_deps(recipe.get_value('requirements/build'))

def construct_graph(directory):
    '''
    Construct a directed graph of dependencies from a directory of recipes

    Annotate dependencies that don't have recipes in that directory
    '''

    g = nx.DiGraph()
    build_numbers = {}
    directory = os.path.abspath(directory)
    assert os.path.isdir(directory)

    # get all immediate subdirectories
    recipe_dirs = next(os.walk(directory))[1]
    recipe_dirs = set(x for x in recipe_dirs if not x.startswith('.'))

    for rd in recipe_dirs:
        recipe_dir = os.path.join(directory, rd)
        try:
            pkg = read_recipe(recipe_dir)
            name = pkg.name()
        except:
            continue

        # add package (in case it has no build deps)
        g.add_node(name, meta=describe_meta(pkg), recipe=recipe_dir)
        for k, d in get_build_deps(pkg).iteritems():
            g.add_edge(name, k)

    return g


def build_order(graph, packages, level=0):
    '''
    Assumes that packages are in graph
    '''

    if packages is None:
        tmp_global = graph.subgraph(graph.nodes())
    else:
        packages = set(packages)
        tmp_global = graph.subgraph(packages)

        if level > 0:
            # for each level, add all deps
            _level = level

            currlevel = packages
            while _level > 0:
                newcurr = set()
                for p in currlevel:
                    newcurr.update(set(graph.successors(p)))
                    tmp_global.add_edges_from(graph.edges_iter(p))
                currlevel = newcurr
                _level -= 1

    #copy relevant node data to tmp_global
    for n in tmp_global.nodes_iter():
        tmp_global.node[n] = graph.node[n]

    return tmp_global, nx.topological_sort(tmp_global, reverse=True)


def check_built(package):
    '''Check to see if package is already built'''
    print("checking if package exists")
    if os.path.exists(os.path.join(CONDA_BUILD_CACHE, package.pkg_fn())):
        return True
    return False


def make_deps(graph, package, dry=False, extra_args='', level=0, autofail=True):
    g, order = build_order(graph, package, level=level)

    # Filter out any packages that don't have recipes
    order = [pkg for pkg in order if g.node[pkg].get('meta')]
    print("Build order:\n{}".format('\n'.join(order)))

    failed = set()
    build_times = {x:None for x in order}
    for pkg in order:
        print("Building ", pkg)
        try:
            # Autofail package if any dependency build failed
            if any(p in failed for p in order):
                print(failed)
                failed_deps = [p for p in g.node[pkg]['meta']['depends'].keys() if p in failed]
                print("Building {} failed because one or more of its dependencies failed to build: ".format(pkg), end=' ')
                print(', '.join(failed_deps))
                failed.add(pkg)
                continue
            build_time = make_pkg(g.node[pkg], dry=dry, extra_args=extra_args)
            build_times[pkg] = build_time
        except KeyboardInterrupt:
            return failed
        except subprocess.CalledProcessError:
            failed.add(pkg)
            continue

    return list(set(order)-failed), list(failed), build_times


def make_pkg(package, dry=False, extra_args=''):
    meta, path = package['meta'], package['recipe']
    print("===========> Building ", path)
    if not dry:
        try:
            extra_args = extra_args.split()
            args = ['conda', 'build', '-q'] + extra_args + [path]
            print("+ " + ' '.join(args))
            p = PopenWrapper(args, time_int=1)
            return p
        except subprocess.CalledProcessError as e:
            print("Build failed with errorcode: ", e.returncode)
            print(e)
            raise


def sequential_build_cli(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
    build_pkgs = parser.add_mutually_exclusive_group()
    build_pkgs.add_argument("-build", action='append', default=[])
    build_pkgs.add_argument("-buildall", action='store_true')
    build_pkgs.add_argument('-json-file-key', default=[], nargs="+",
                            help="Example: -json-file-key package_tree.js libnetcdf pysam")
    parser.add_argument("-dry", action='store_true', default=False,
                              help="Dry run")
    parser.add_argument("-api", action='store_true', dest='recompile',
                              default=False)
    parser.add_argument("-args", action='store', dest='cbargs', default='')
    parser.add_argument("-l", type=int, action='store', dest='level', default=0)
    parser.add_argument("-noautofail", action='store_false', dest='autofail', default=True)
    parser.add_argument('--targetnum', '-t',
                        type=int,
                        help="Target number of packages in each subtree-build.")
    if parse_this is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(parse_this)
    print('Running build2.py with args of', args)
    if getattr(args, 'json_file_key', None):
        assert len(args.json_file_key) == 2, 'Should be 2 args: json_filename key'
    return args


def pre_build_clean_up(args):
    '''Copies files from patterns like:

    ./special_cases/<package-name>/run_test.sh

    to

    args.path/<package-name>/run_test.sh

    (Helpful if anaconda-build needs mods)
    '''
    special = os.path.join(os.path.dirname(__file__), 'special_cases')
    for dirr in os.listdir(special):
        for fil in os.listdir(os.path.join(special, dirr)):
            full_file = os.path.join(special, dirr, fil)
            if not os.path.exists(os.path.join(args.path, dirr)):
                continue
            target = os.path.join(args.path, dirr, fil)
            print('Copy', full_file, 'to', target)
            print('Copy', full_file, 'to', target+'_removed')
            shutil.copy(full_file, target + '_removed')
            shutil.copy(full_file, target)


def sequential_build_main(parse_this=None):
    from protoci.split import make_package_tree_main
    args = sequential_build_cli(parse_this=parse_this)
    g = construct_graph(args.path)
    pre_build_clean_up(args)
    try:
        if args.buildall:
            args.build = None
        if args.json_file_key:
            with open(args.json_file_key[0], 'w') as f:
                command_line_args = ['.', '--split-files',
                                    'not_used.js', '-t',
                                    str(args.targetnum)]
                hi_level_builds = make_package_tree_main(parse_this=command_line_args,
                                                          exit=False)
                packages = hi_level_builds[args.json_file_key[1]]
                packages += args.json_file_key[1:]
                for package in packages:
                    package = g.node[package]
                    if not 'meta' in package:
                        continue
                    make_pkg(package, dry=args.dry, extra_args=args.cbargs)
                sys.exit(0)
        success, fail, times = make_deps(g, args.build, args.dry,
                                         extra_args=args.cbargs,
                                         level=args.level,
                                         autofail=args.autofail)
        print("BUILD SUMMARY:")
        print("SUCCESS: [{}]".format(', '.join(success)))
        print("FAIL: [{}]".format(', '.join(fail)))

        # Sum memory usage and print elapsed times.
        r, v, e = 0, 0, 0
        print("Build stats: Package, Elapsed time, Mem Usage, Disk Usage")
        for k, i in times.items():
            r, v = max(i.rss, r), max(i.vms, r)
            e += i.elapsed
            print("{}\t\t{:.2f}s\t{}\t{}".format(k, e, bytes2human(i.rss), bytes2human(i.disk)))
        r, v = bytes2human(r), bytes2human(v)
        print("Max Memory Usage (RSS/VMS): {}/{}".format(r, v))
        print("Total elapsed time: {:.2f}m".format(e/60))

        sys.exit(len(fail))
    except:
        raise


def difference_build_cli(parse_this=None):
    parser = argparse.ArgumentParser(description="Does git diff to determine build order.")
    # add arguments here related to git diff options
    if not parse_this:
        return parser.parse_args()
    return parser.parse_args(parse_this)

def difference_build_main(parse_this=None):
    args = difference_build_cli(parse_this=parse_this)
    print('Make differencing of git function here.')
    return