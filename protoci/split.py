import argparse
from collections import defaultdict
import json
import sys

import networkx as nx

from protoci.build2 import construct_graph

def successors_iter(g, s, nodes):
    for s in sorted(g.successors(s)):
        nodes.append(s)
        for s in tuple(successors_iter(g, s, nodes)):
            nodes.append(s)
    nodes2 = []
    for n in nodes:
        if nodes2.count(n) == 0:
            nodes2.append(n)
    return nodes2

def coalesce(hi_level_builds, targetnum):
    coalesced = defaultdict(lambda: [])
    counts = [(k, len(v)) for k, v in hi_level_builds.items()]
    group = []
    for key, count in sorted(counts, key=lambda x:(x[1], x[0])):
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
    toposort = nx.topological_sort(g)
    packages_covered = defaultdict(lambda:0)
    degrees = dict(g.degree_iter())

    hi_level_builds = {}
    for hi_level in nx.topological_sort(g):
        if hi_level in packages_covered:
            continue
        succ = tuple(successors_iter(g, hi_level, []))
        for s in succ:
            packages_covered[s] += 1
        packages_covered[hi_level] += 1
        topo_order = [(s, toposort.index(s)) for s in succ]
        succ_order = sorted(topo_order, key=lambda x: -x[1])
        hi_level_builds[hi_level] = [_[0] for _ in succ_order]
    hi_level_builds = coalesce(hi_level_builds, targetnum)
    with open(split_file, 'w') as f:
        f.write(json.dumps(hi_level_builds))
    return hi_level_builds


def make_package_tree_cli(parse_this=None):
    parser = argparse.ArgumentParser(description="Split a package tree to a json hierarchy")
    parser.add_argument('path',
                        help="Path to directory of packages")
    parser.add_argument('-t','--targetnum',
                        type=int,
                        default=10,
                        help="How many packages in one anaconda "
                             "build submission typically.")
    parser.add_argument('-s','--split-files',
                        type=str,
                        default="package_tree.js")
    if not parse_this:
        return parser.parse_args()
    return parser.parse_args(parse_this)

def make_package_tree_main(parse_this=None, exit=True):
    args = make_package_tree_cli(parse_this=parse_this)
    g = construct_graph(args.path)
    hi_level_builds = split_graph(g, args.targetnum, args.split_files)
    print("See ", args.split_files, 'for split packages')
    if exit:
        sys.exit(0)
    return hi_level_builds

