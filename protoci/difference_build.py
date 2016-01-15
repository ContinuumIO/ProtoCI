import argparse
import sys

from protoci.build2 import (construct_graph, build_cli)
from protoci.sequential_build import sequential_build_main

def difference_build_cli(parse_this=None):
    parser = argparse.ArgumentParser(description="Does git diff to determine build order.")
    # add arguments here related to git diff options
    parser.add_argument('path',
                        help='Top level dir of packages. Look for all changes.',
                        type=str)

    if not parse_this:
        args = parser.parse_args()
    args = parser.parse_args(parse_this)
    parse_this = '{} --all-diffs'.format(args.path)
    return build_cli(parse_this=parse_this)

def difference_build_main(parse_this=None):
    args = difference_build_cli(parse_this=parse_this)
    g = construct_graph(args.path, filter_by_git_change=True)
    return sequential_build_main(parse_this=parse_this, g=g)