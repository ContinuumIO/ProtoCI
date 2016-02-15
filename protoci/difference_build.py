from __future__ import print_function
import argparse
import json
import subprocess
import sys

from protoci.build2 import (construct_graph, build_cli,
                            last_changed_git_branch)
from protoci.sequential_build import sequential_build_main

def checkout_last_changed(args):
    branch = last_changed_git_branch(args.path)
    cmd_line = ['git', 'checkout', branch]
    print(cmd_line)
    proc = subprocess.Popen(cmd_line,
                            cwd=args.path,
                            stdout=subprocess.PIPE)
    if proc.wait():
        raise ValueError('Failed on git checkout ', branch)
    print(proc.stdout.read().decode())

def difference_build_cli(parse_this=None):
    parser = argparse.ArgumentParser(description="Does git diff "
                                                 "to determine build order.")
    # add arguments here related to git diff options
    parser.add_argument('path',
                        help='Top level dir of packages. Look for all changes.',
                        type=str)
    parser.add_argument('-dry',
                        action='store_true',
                        help='Dry run (store_true)')
    parser.add_argument('-depth',
                        default=1,
                        type=int,
                        help="Search depth for packages affected "
                             "by git changes. (1 = 1 node away changes)")
    if not parse_this:
        args = parser.parse_args()
    args = parser.parse_args(parse_this)
    parse_this = [args.path]
    if args.dry:
        parse_this.append('-dry')
    args2 = build_cli(parse_this=parse_this)
    vars(args2).update(vars(args))
    return args2

def expand_dirty_label(g, changed=None):
    changed = changed or set()
    for node, value in g.node.items():
        if value.get('dirty'):
            changed.add(node)
            for successor in g.predecessors(node):
                changed.add(successor)
                g.node[successor]['dirty'] = True
    return changed

def difference_build_main(parse_this=None):
    args = difference_build_cli(parse_this=parse_this)
    g = construct_graph(args.path, filter_by_git_change=True)
    changed = set()
    for repeat in range(args.depth):
        changed = expand_dirty_label(g, changed)
    print('Full packages to test: ', json.dumps(list(changed)))
    return sequential_build_main(parse_this=parse_this,
                                 g=g,
                                 args=None)
