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
        # set returncode to a bad one
        # in case it is never defined
        # after here.
        self.returncode = 173
        self.disk = None

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
                self.returncode = _popen.poll()
                if _popen.returncode is not None:
                    # without this if block
                    # builds hang
                    try:
                        _popen.kill()
                    except psutil.NoSuchProcess:
                        pass
                    break
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

def last_changed_git_branch(git_root):
    args = ['git', 'for-each-ref',
            '--sort=-committerdate', 'refs/heads/',]
    proc = subprocess.Popen(args,
                            cwd=git_root,
                            stdout=subprocess.PIPE)
    if proc.wait():
        raise ValueError('Bad return code '
                         'from git branch sort', proc.poll())
    head_1 = proc.stdout.read().decode().splitlines()[0]
    branch = head_1.split()[-1]
    print('Last changed branch: ', branch)
    return branch

def git_changed_files(git_rev, git_root=''):
    """
    Get the list of files changed in a git revision and return a list of package directories that have been modified.
    """
    proc = subprocess.Popen(['git', 'diff-tree',
                              '--no-commit-id', '--name-only',
                              '-r', git_rev
                              ],
                              cwd=git_root,
                              stdout=subprocess.PIPE)
    if proc.wait():
        raise ValueError('Bad git return code: {}'.format(proc.poll()))
    files = proc.stdout.read().decode().splitlines()
    too_short = ('\\','/')
    changed = {os.path.dirname(f) for f in files}
    changed = {f for f in changed if f and f not in too_short}
    return changed

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

def construct_graph(directory, filter_by_git_change=True):
    '''
    Construct a directed graph of dependencies from a directory of recipes

    Annotate dependencies that don't have recipes in that directory
    '''
    print('construct_graph with args: ', directory, filter_by_git_change)
    g = nx.DiGraph()
    build_numbers = {}
    directory = os.path.abspath(directory)
    assert os.path.isdir(directory)

    # get all immediate subdirectories
    other_top_dirs = [d for d in os.listdir(directory)
                    if os.path.isdir(os.path.join(directory, d)) and
                    not os.path.exists(os.path.join(directory, d, 'meta.yaml')) and
                    not d.startswith('.')]
    recipe_dirs = next(os.walk(directory))[1]
    for top in other_top_dirs:
        next_level = next(os.walk(os.path.join(directory, top)))[1]
        recipe_dirs += [os.path.join(top, n) for n in next_level]
    recipe_dirs = set(x for x in recipe_dirs if not x.startswith('.'))
    if filter_by_git_change:
        changed_recipes = git_changed_files('HEAD', git_root=directory)
        print('changed_recipes {}'.format(changed_recipes))
    for rd in recipe_dirs:
        recipe_dir = os.path.join(directory, rd)
        try:
            pkg = read_recipe(recipe_dir)
            name = pkg.name()
        except:
            continue

        # add package (in case it has no build deps)
        if filter_by_git_change:
            _dirty = False
            if rd in changed_recipes:
                _dirty = True
        else:
            _dirty = True
        g.add_node(name, meta=describe_meta(pkg), recipe=recipe_dir, dirty=_dirty)
        for k, d in get_build_deps(pkg).items():
            g.add_edge(name, k)
    return g

def dirty(graph, implicit=True):
    """
    Return a set of all dirty nodes in the graph.

    These include implicit and explicit dirty nodes.
    """
    # Reverse the edges to get true dependency
    dirty_nodes = {n for n, v in graph.node.items() if v.get('dirty', False)}
    if not implicit:
        return dirty_nodes

    # Get implicitly dirty nodes (all of the packages that depend on a dirty package)
    dirty_nodes.update(*map(set, (graph.predecessors(n) for n in dirty_nodes)))
    return dirty_nodes

def build_order(graph, packages, level=0, filter_by_git_change=True):
    '''
    Assumes that packages are in graph.
    Builds a temporary graph of relevant nodes and returns it topological sort.

    Relevant nodes selected in a breadth first traversal sourced at each pkg in packages.

    Values expected for packages is one of None, sequence:
       None: build the whole graph
       empty sequence: build nodes marked dirty
       non-empty sequence: build nodes in sequence
    '''

    if packages is None and not filter_by_git_change:
        tmp_global = graph.subgraph(graph.nodes())
    else:
        if packages:
            packages = set(packages)
        else:
            packages = dirty(graph)
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

def make_deps(graph, package, dry=False, extra_args='',
              level=0, autofail=True, jobtimeout=3600,
              timeoutbuffer=600):
    g, order = build_order(graph, package, level=level)
    # Filter out any packages that don't have recipes
    order = [pkg for pkg in order if g.node[pkg].get('meta')]
    print("Build order:\n{}".format('\n'.join(order)))
    elapsed = 0.0
    failed = set()
    not_tested = set()
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
            if build_time is None:
                failed.add(pkg)
            elapsed += build_times[pkg].elapsed
            if elapsed > jobtimeout - timeoutbuffer:
                idx = order.index(pkg) + 1
                if idx >= len(order):
                    not_tested = set()
                else:
                    not_tested = set(order[idx:])
                print('TIMEOUT within protoci, NOT_TESTED', not_tested)
                break
            if build_times[pkg].returncode:
                failed.add(pkg)
        except KeyboardInterrupt:
            print('KeyboardInterrupt')
            break
        except subprocess.CalledProcessError:
            failed.add(pkg)
            continue

    return list(set(order) - failed - not_tested), list(failed), list(not_tested), build_times


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
    else:
        return PopenWrapper(['echo', '-dry', '(dry run)'])


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

def build_cli(parse_this=None):
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
    parser.add_argument('--packages', '-p',
                        default=[],
                        nargs="+",
                        help="Rather than determine tree, build the --packages in order")
    parser.add_argument('-depth',
                        required=False,
                        type=int,
                        help="Used only in git diff (depth of changed packages)")
    if parse_this is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(parse_this)
    if not args.build:
        args.build = None
    print('Running build2.py with args of', args)
    if getattr(args, 'json_file_key', None):
        assert len(args.json_file_key) == 2, 'Should be 2 args: json_filename key'
    return args
