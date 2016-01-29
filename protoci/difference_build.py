import argparse
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
    if not parse_this:
        args = parser.parse_args()
    args = parser.parse_args(parse_this)
    parse_this = [args.path]
    if args.dry:
        parse_this.append('-dry')
    return build_cli(parse_this=parse_this)


def difference_build_main(parse_this=None):
    args = difference_build_cli(parse_this=parse_this)
    # actually this may not be needed in CI: checkout_last_changed(args)
    #      (I think that is done automatically)
    g = construct_graph(args.path, filter_by_git_change=True)
    return sequential_build_main(parse_this=parse_this,
                                 g=g,
                                 args=None)
