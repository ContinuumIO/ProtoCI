from __future__ import print_function
"""
build_protoci.py creates conda packages of
protoci for all operating systems and python versions.

Usage:

anaconda login
python build_protoci.py path anaconda_user

where:
    conda build . is run at path
    and
    anaconda_user is the upload user

"""
import os
import shutil
from subprocess import *
import sys
import time

dists = ['linux-32','linux-64','osx-64','win-32', 'win-64']
def build_protoci(input_args):
    path = input_args.path
    env = os.environ.copy()
    retvals = []
    for CONDA_PY in ('27', '34', '35'):
        print('Clean build dirs')
        for dist_dir in dists:
            dist_dir = os.path.join(path, dist_dir)
            if os.path.exists(dist_dir):
                shutil.rmtree(dist_dir)
        env['CONDA_PY'] = CONDA_PY
        args = ['conda', 'build', '.','--no-anaconda-upload']
        print(args)
        print("CONDA_PY", CONDA_PY)
        proc = Popen(args,
                     cwd=path, stdout=PIPE,
                     stderr=STDOUT, env=env)
        out = []
        while proc.poll() is None:
            out.append(proc.stdout.readline().rstrip())
            print(out[-1])
            time.sleep(0.02)
        pos = len(out)
        out.extend(proc.stdout.readlines())
        if proc.wait():
            print('FAILED conda build . ', CONDA_PY)
            print(out)
            return proc.poll()
        print("conda build . (OK) for", CONDA_PY)
        files = []
        for line in out:
            if line.startswith("#") and 'anaconda' in line and 'upload' in line:
                f = line.split()[-1]
                if os.path.exists(f):
                    files.append(f)
        print('convert: ', files)
        for file in files:
            proc = Popen(['conda', 'convert', '--platform', 'all', file],
                  stdout=PIPE, stderr=STDOUT, cwd=path, env=env)
            proc.wait()
            out = proc.stdout.read().decode()
            retvals.append(proc.poll())
            if retvals[-1]:
                print('Failed on conda convert')
                print(out)
            else:
                print("Conversion ok for", file)
                for dist in dists:
                    dist_dir = os.path.join(path, dist)
                    for dist_file in os.listdir(dist_dir):
                        env = os.environ.copy()
                        env['CONDA_PY'] = CONDA_PY
                        proc = Popen(['anaconda', 'upload',
                               '--user', input_args.user,
                               os.path.abspath(os.path.join(dist_dir, dist_file)),
                               '--force',],
                               cwd=path)
                        if proc.wait():
                            print('Failed on anaconda upload')
                            sys.exit(proc.poll())
    return 1 if not len(retvals) else max(retvals)

def cli():
    import argparse
    parser = argparse.ArgumentParser(description="Take path and user name.")
    parser.add_argument('path',
                        help="Path to repo to conda build on locally")
    parser.add_argument('user',
                        help="anaconda user")
    return parser.parse_args()

def main():
    args = cli()
    sys.exit(build_protoci(args))

if __name__ == "__main__":
    main()