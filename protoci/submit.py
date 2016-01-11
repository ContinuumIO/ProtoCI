import argparse
import json
import subprocess
import sys

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
    with open(os.path.join(os.path.dirname(__file__), 'binstar_template.yml')) as f:
        contents = f.read()
        t = jinja2.Template(contents)
        package = 'protoci-' + key
        info = (os.path.basename(js_file), key)
        platforms = "".join(" - {}\n".format(p) for p in args.platforms)
        binstar_yml = t.render(PACKAGE=package,
                               USER=args.user,
                               PLATFORMS=platforms,
                               BUILD_ARGS='./ build ' +\
                                          '-json-file-key {0} {1}'.format(*info))
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

def pre_submit_clean_up(args):
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

    this_file = os.path.basename(__file__)
    build2_in_other_dir = os.path.abspath(os.path.join(args.path, this_file))
    shutil.copy(__file__, build2_in_other_dir)
    print('Copy',__file__,'to', build2_in_other_dir)
    package_tree_file = os.path.abspath(args.full_json or args.json_file_key[0])
    n = datetime.datetime.now()
    datestr = "_".join(map(str, (n.year, n.month, n.day, n.hour, n.minute, n.second)))
    branch_name = 'build_' + datestr
    print('Make a scratch git branch in', os.path.abspath(args.path))
    subprocess.check_output(['git', 'checkout', '-b', branch_name], cwd=args.path)
    subprocess.check_output(['git', 'add', build2_in_other_dir, package_tree_file], cwd=args.path)
    print(subprocess.Popen(
          ['git', 'commit', '-m',
          'commit build2.py and the package json for anaconda-build'],
          cwd=args.path).communicate())


def submit_helper(args):
    pre_submit_clean_up(args)
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
    if not parse_this:
        return parser.parse_args()
    return parser.parse_args(parse_this)


def submit_main(parse_this=None, exit=True):
    args = submit_cli(parse_this=parse_this)
    ret_val = submit_helper(args)
    if exit:
        sys.exit(ret_val)
