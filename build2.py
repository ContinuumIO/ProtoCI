#!/usr/bin/env python
from __future__ import print_function

import argparse
from collections import defaultdict
import json
import os
import subprocess
import time
import networkx as nx
import sys



from conda_build.metadata import parse, MetaData

CONDA_BUILD_CACHE=os.environ.get("CONDA_BUILD_CACHE")


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

def successors_iter(g, s, nodes):
    for s in g.successors(s):
        nodes.add(s)
        for s in tuple(successors_iter(g, s, nodes)):
            nodes.add(s)
    return nodes

def coalesce(hi_level_builds, targetnum):
    coalesced = defaultdict(lambda: [])
    counts = [(k, len(v)) for k, v in hi_level_builds.items()]
    group = []
    for key, count in sorted(counts, key=lambda x:x[1]):
        group.append(hi_level_builds[key] + [key])
        if sum(map(len, group)) >= targetnum:
            for g in group:
                if g == key:
                    continue
                coalesced[key] += [gi for gi in g if gi not in coalesced[key] and gi != key]
            group = []
    if group:
        for g in group:
            coalesced[key] += [gi for gi in g if gi not in coalesced[key] and gi != key]
    return coalesced

def split_graph(g, targetnum, split_file):
    g = g.copy()
    packages_covered = defaultdict(lambda:0)
    degrees = dict(g.degree_iter())

    hi_level_builds = {}
    for hi_level in nx.topological_sort(g):
        if hi_level in packages_covered:
            continue
        succ = tuple(successors_iter(g, hi_level, set()))
        for s in succ:
            packages_covered[s] += 1
        packages_covered[hi_level] += 1
        succ_order = sorted(((s, degrees[s]) for s in succ),
                            key=lambda x:x[1])
        hi_level_builds[hi_level] = [_[0] for _ in succ_order]
    hi_level_builds = coalesce(hi_level_builds, targetnum)
    with open(split_file, 'w') as f:
        f.write(json.dumps(hi_level_builds))
    return hi_level_builds

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
            build_times[pkg] = 30 + int(5*round(build_time/5))
        except KeyboardInterrupt:
            return failed
        except subprocess.CalledProcessError:
            failed.add(pkg)
            continue

    return list(set(order)-failed), list(failed), build_times


def make_pkg(package, dry=False, extra_args=''):
    meta, path = package['meta'], package['recipe']
    print(meta, path)
    #print(" Building %s ".center(80, '=') % meta.name())
    if not dry:
        try:
            extra_args = extra_args.split()
            args = ['conda', 'build'] + extra_args + [path]
            print("+ " + ' '.join(args))
            start = time.time()
            subprocess.check_call(args)
            end = time.time()
            return end-start
        except subprocess.CalledProcessError as e:
            print("Build failed with errorcode: ", e.returncode)
            print(e)
            raise

def cli():

    p = argparse.ArgumentParser()
    p.add_argument("path", default='.')
    subp = p.add_subparsers(help="Build or split to make json of package "
                                 "order/grouping. \n\tChoices: %(choices)s")
    build_parser = subp.add_parser('build')
    build_pkgs = build_parser.add_mutually_exclusive_group()
    build_pkgs.add_argument("-build", action='append', default=[])
    build_pkgs.add_argument("-buildall", action='store_true')
    build_pkgs.add_argument('-json-file-key', default=[], nargs=2)
    build_parser.add_argument("-dry", action='store_true', default=False)
    build_parser.add_argument("-api", action='store_true', dest='recompile', default=False)
    build_parser.add_argument("-args", action='store', dest='cbargs', default='')
    build_parser.add_argument("-l", type=int, action='store', dest='level', default=0)
    build_parser.add_argument("-t", action='store_true', dest='t', default=False)
    build_parser.add_argument("-noautofail", action='store_false', dest='autofail', default=True)
    split_parser = subp.add_parser('split')
    split_parser.add_argument('-t','--targetnum', type=int, default=10, help="How many packages in one anaconda build submission typically.")
    split_parser.add_argument('-s','--split-files',type=str)
    args = p.parse_args()
    print('Running build2.py with args of', args)
    if getattr(args, 'json_file_key', None):
        assert len(args.json_file_key) == 2, 'Should be 2 args: json_filename key'
    return args

if __name__ == "__main__":

    args = cli()
    print("%s" % (getattr(args,'build','')))
    print("-------------------------------")

    g = construct_graph(args.path)
    if getattr(args, 'split_files', None) is not None:
        split_graph(g, args.targetnum, args.split_files)
        print("See ", args.split_files, 'for split packages')
        sys.exit(0)
    try:
        if args.buildall:
            args.build = None
        if args.json_file_key:
            with open(args.json_file_key[0]) as f:
                args.build = json.load(f)[args.json_file_key[1]]
                args.build += [args.json_file_key[1]]

        success, fail, times = make_deps(g, args.build, args.dry, extra_args=args.cbargs, level=args.level, autofail=args.autofail)

        print("BUILD STATUS:")
        print("SUCCESS: [{}]".format(', '.join(success)))
        print("FAIL: [{}]".format(', '.join(fail)))

        if args.t:
            print(times)

        sys.exit(len(fail))
    except:
        raise
