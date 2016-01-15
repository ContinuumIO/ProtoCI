import argparse
import sys

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