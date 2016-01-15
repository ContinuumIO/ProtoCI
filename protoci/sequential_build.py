import argparse
import sys

from protoci.build2 import (make_pkg, make_deps,
                            construct_graph, pre_build_clean_up,
                            bytes2human, )

def sequential_build_cli(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
    build_pkgs = parser.add_mutually_exclusive_group()
    build_pkgs.add_argument("-build", action='append', default=[])
    build_pkgs.add_argument("-buildall", action='store_true')
    build_pkgs.add_argument('-json-file-key', default=[], nargs="+",
                            help="Example: -json-file-key package_tree.js libnetcdf pysam")
    parser.add_argument("-dry", action='store_true', default=False,
                              help="Dry run")
    parser.add_argument("-api", action='store_true', dest='recompile',
                              default=False)
    parser.add_argument("-args", action='store', dest='cbargs', default='')
    parser.add_argument("-l", type=int, action='store', dest='level', default=0)
    parser.add_argument("-noautofail", action='store_false', dest='autofail', default=True)
    parser.add_argument('--targetnum', '-t',
                        type=int,
                        help="Target number of packages in each subtree-build.")
    parser.add_argument('--packages', '-p',
                        default=[],
                        nargs="+",
                        help="Rather than determine tree, build the --packages in order")
    if parse_this is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(parse_this)
    print('Running build2.py with args of', args)
    if getattr(args, 'json_file_key', None):
        assert len(args.json_file_key) == 2, 'Should be 2 args: json_filename key'
    return args


def sequential_build_main(parse_this=None):
    '''
        sequential_build_main(parse_this=None)
        Params:
            parse_this = None or iterable of sys.argv like
                         list to sequential_build_cli

        Notes: This operates in several modes:
            if args.packages is a list of packages:
                build them in order from start to finish of list
                exit 0 if no exception
            elif args.json_file_key is an list/tuple:
                1st element: json file name
                2nd elements to end: keys in that json dict in json file
                    (keys are high level packages, values are
                     dependencies to build in order, followed by
                     the key package)
            else:
                using args.build or args.buildall
                to build a package or packages
                with
    '''
    from protoci.split import make_package_tree_main
    args = sequential_build_cli(parse_this=parse_this)
    g = construct_graph(args.path)
    pre_build_clean_up(args)
    try:
        if args.buildall:
            args.build = None
        if args.packages is None:
            if args.json_file_key:
                json_file, hi_level_list = args.json_file_key[0], args.json_file_key[1:]
                with open(json_file, 'r') as f:
                    hi_level_builds = json.load(f)
                packages = []
                # args.json_file_key gave a list
                # of keys in the json file
                # from which to build a list in order
                # if args.json_file_key is longer than
                # 2 elements, items at idx 1: are keys
                # in the json
                for hi_level in hi_level_list:
                    # build depends in topo order
                    packages.extend(hi_level_builds[hi_level])
                    # build the hi level package that is key in json
                    packages.append(hi_level)
            else:
                # using -build or -buildall
                packages = []
        else:
            # a list of packages within args.path dir
            # was given and is being built from start
            # of list to end
            packages = args.packages
        if packages:
            for package in packages:
                package = g.node[package]
                if not 'meta' in package:
                    continue
                make_pkg(package, dry=args.dry, extra_args=args.cbargs)
            sys.exit(0)
        # using -build or -buildall flags
        success, fail, times = make_deps(g, args.build, args.dry,
                                         extra_args=args.cbargs,
                                         level=args.level,
                                         autofail=args.autofail)
        print("BUILD SUMMARY:")
        print("SUCCESS: [{}]".format(', '.join(success)))
        print("FAIL: [{}]".format(', '.join(fail)))

        # Sum memory usage and print elapsed times.
        r, v, e = 0, 0, 0
        print("Build stats: Package, Elapsed time, Mem Usage, Disk Usage")
        for k, i in times.items():
            r, v = max(i.rss, r), max(i.vms, r)
            e += i.elapsed
            print("{}\t\t{:.2f}s\t{}\t{}".format(k, e, bytes2human(i.rss), bytes2human(i.disk)))
        r, v = bytes2human(r), bytes2human(v)
        print("Max Memory Usage (RSS/VMS): {}/{}".format(r, v))
        print("Total elapsed time: {:.2f}m".format(e/60))

        sys.exit(len(fail))
    except:
        raise
