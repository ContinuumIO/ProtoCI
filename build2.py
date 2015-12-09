#!/usr/bin/env python
from __future__ import print_function

import os
import subprocess
import time
import networkx as nx

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


if __name__ == "__main__":
    import sys
    import argparse
    
    p = argparse.ArgumentParser()
    build_pkgs = p.add_mutually_exclusive_group()
    build_pkgs.add_argument("-build", action='append', default=[])
    build_pkgs.add_argument("-buildall", action='store_true')
    p.add_argument("-dry", action='store_true', default=False)
    p.add_argument("-api", action='store_true', dest='recompile', default=False)
    p.add_argument("-args", action='store', dest='cbargs', default='')
    p.add_argument("-l", type=int, action='store', dest='level', default=0)
    p.add_argument("-t", action='store_true', dest='t', default=False)
    p.add_argument("-noautofail", action='store_false', dest='autofail', default=True)
    p.add_argument("path", default='.')
    args = p.parse_args()
    
    print("%s" % (args.build))
    print("-------------------------------")
    
    g = construct_graph(args.path)

    try:
        if args.buildall:
            args.build = None
        success, fail, times = make_deps(g, args.build, args.dry, extra_args=args.cbargs, level=args.level, autofail=args.autofail)

        print("BUILD STATUS:")
        print("SUCCESS: [{}]".format(', '.join(success)))
        print("FAIL: [{}]".format(', '.join(fail)))
        
        if args.t:
            print(times)
        
        sys.exit(len(fail))
    except:
        raise