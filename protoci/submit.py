import argparse
import datetime
import json
import shutil
import subprocess
import os
import sys

from protoci.build2 import pre_build_clean_up

def submit_one(args):
    '''
    Adjusts binstar_template.yml
    base on
        user
        queue
        build arguments
        platforms
    Comes up with a package name for user
    Creates package if it doesn't exist
    Submits package
    Prints out the command you need to tail the build
    returns 0 if okay
    '''
    import jinja2
    js_file, key = args.json_file_key
    with open(js_file, 'r') as f:
        js = json.load(f)
    with open(os.path.join(os.path.dirname(__file__), 'data', 'binstar_template.yml')) as f:
        packages = js[key] + [key]
        contents = f.read()
        t = jinja2.Template(contents)
        package = 'protoci-' + key
        info = (os.path.basename(js_file), key)
        platforms = "".join(" - {}\n".format(p) for p in args.platforms)
        packages = " ".join('"{}"'.format(p) for p in packages)
        build_args = '{} --packages {}'.format('.', packages)
        if args.dry:
            build_args += ' -dry'
        binstar_yml = t.render(PACKAGE=package,
                               USER=args.user,
                               PLATFORMS=platforms,
                               BUILD_ARGS=build_args)
        with open(os.path.join(args.path, '.binstar.yml'), 'w') as f:
            f.write(binstar_yml)
    full_package = '{0}/{1}'.format(args.user, package)
    cmd = ['anaconda', 'build', 'list-all', full_package]
    print('Check to see if', full_package, 'exists:', cmd)
    proc = subprocess.Popen(cmd)
    if proc.wait():
        cmd = ['anaconda', 'package','--create', full_package]
        print("prepare to create package", cmd)
        if not args.dry:
            create = subprocess.Popen(cmd, cwd=args.path)
            if create.wait():
                raise ValueError('Could not create {}'.format(full_package))

    user_queue = '{0}/{1}'.format(args.user, args.queue)
    cmd = ['anaconda', 'build',
           'submit', './', '--queue',
           user_queue]
    for label in getattr(args, 'labels', []) or []:
        cmd.extend(('--label', label))
    print('prepare to submit', cmd)
    if args.dry:
        return 0
    proc =  subprocess.Popen(cmd, cwd=args.path, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    ret = proc.wait()
    out = proc.stdout.read().decode()
    tail = [line for line in out.split('\n')
            if 'tail' in line and full_package in line]
    if len(tail):
        tail = tail[0]
    else:
        print("Apparently something wrong with:", out)
        time.sleep(10)
    print('TAIL:\t', tail)
    return ret


def submit_full_json(args):
    ''' Given -full-json, run every package tree
    in a json that was created by split action, typically
    called package_tree.js
    '''
    with open(args.full_json, 'r') as f:
        tree = json.load(f)
        print('{} high level packages'.format(len(tree)))
        print('\twith total packages:',
              len(tree) + sum(map(len, tree.values())))
        for key in tree:
            print('Key: ', key, len(tree[key])+1, 'packages to build/test')
            args.json_file_key = (args.full_json, key)
            submit_one(args)
    return 0


def submit_helper(args):
    pre_build_clean_up(args)
    if args.full_json:
        return submit_full_json(args)
    else:
        assert len(args.json_file_key) >= 2
        arg1 = args.json_file_key[0]
        hi_level = args.json_file_key[1:]
        for key in hi_level:
            args.json_file_key = (arg1, key)
            ret_val = submit_one(args)
            if ret_val:
                return ret_val
    return 0


def submit_cli(parse_this=None):

    parser = argparse.ArgumentParser(description="Help submitting packages adhoc for anaconda-build testing")
    parser.add_argument('path',
                        help="Path to a directory of packages")
    json_read_choice = parser.add_mutually_exclusive_group()
    json_read_choice.add_argument('-json-file-key',
                                  default=[],
                                  nargs=2,
                                  help="Example: -json-file-key package_tree.js libnetcdf")
    json_read_choice.add_argument('-full-json',
                                  type=str,
                                  help="Build all packages named in json of splits")
    parser.add_argument('-user',
                        default='conda-team',
                        help="Anaconda username. Default: %(default)s")
    parser.add_argument('-queue',
                        default='build_recipes',
                        help="Anaconda build queue. Default: %(default)s")
    parser.add_argument('-dry',
                        action='store_true',
                        help='Dry run')
    parser.add_argument('-platforms',
                        required=True,
                        help="Some of all of %(default)s",
                        default=['osx-64', 'linux-64','win-64'],
                        nargs="+")
    parser.add_argument('--targetnum','-t',
                        help="The --targetnum argument that was given to protoci-split-packages",
                        required=True)
    parser.add_argument('--labels',
                        help="The anaconda.org label(s) to apply "
                             "(formerly called channels).\n\tDefault: %(default)s",
                        nargs="+",
                        default=['dev'])
    if not parse_this:
        return parser.parse_args()
    return parser.parse_args(parse_this)


def submit_main(parse_this=None, exit=True):
    args = submit_cli(parse_this=parse_this)
    print('Running submit with args: {}'.format(args))
    ret_val = submit_helper(args)
    if exit:
        sys.exit(ret_val)

