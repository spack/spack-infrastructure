import argparse
import re

STACKS_TO_EXCLUDE = [
    #                 stack               | # total    | # missing from |  recent   |  exclude from   | # in stack missing |
    #                                     |  in stack  |    top level   | pipeline? | patching holes? | meta or archive    |
    #-------------------------------------------------------------------|-----------------------------|--------------------|
    "aws-ahug-aarch64",                 #    9240    |     9240       |    [ ]    |      [ ]        |        610         |
    "aws-ahug",                         #    4301    |     4301       |    [ ]    |      [ ]        |          0         |
    "aws-isc-aarch64",                  #    4566    |     3666       |    [x]    |      [ ]        |          0         |
    "aws-isc",                          #    2298    |     1845       |    [x]    |      [ ]        |          0         |
    "aws-pcluster-icelake",             #     150    |      150       |    [x]    |      [ ]        |          0         |
    "aws-pcluster-neoverse_n1",         #     188    |      t88       |    [ ]    |      [ ]        |          1         |
    "aws-pcluster-neoverse_v1",         #     312    |      236       |    [ ]    |      [ ]        |          0         |
    "aws-pcluster-skylake",             #     181    |      181       |    [ ]    |      [ ]        |          0         |
    "aws-pcluster-x86_64_v4",           #     566    |      426       |    [x]    |      [ ]        |          0         |
    "build_systems",                    #     384    |      310       |    [x]    |      [ ]        |          0         |
    "data-vis-sdk",                     #    6030    |     4852       |    [x]    |      [ ]        |          0         |
    # "deprecated",                       #      20    |       15       |    [x]    |      [ ]        |          0         |
    "developer-tools-manylinux2014",    #    1049    |      740       |    [x]    |      [ ]        |          0         |
    "developer-tools",                  #    1070    |      871       |    [x]    |      [ ]        |          0         |
    "e4s-aarch64",                      #    2295    |     2295       |    [ ]    |      [ ]        |          0         |
    "e4s-arm",                          #    4973    |     4973       |    [ ]    |      [ ]        |          0         |
    "e4s-cray-rhel",                    #    1795    |     1300       |    [x]    |      [ ]        |          0         |
    "e4s-cray-sles",                    #    1260    |      908       |    [x]    |      [ ]        |          0         |
    "e4s-neoverse-v2",                  #   10473    |     8309       |    [x]    |      [ ]        |          0         |
    "e4s-neoverse_v1",                  #   10532    |     8377       |    [x]    |      [ ]        |          0         |
    "e4s-oneapi",                       #    8388    |     6119       |    [x]    |      [ ]        |          0         |
    "e4s-power",                        #    8822    |     7019       |    [x]    |      [ ]        |          0         |
    "e4s-rocm-external",                #    2770    |     2153       |    [x]    |      [ ]        |          0         |
    "e4s",                              #   12399    |     9882       |    [x]    |      [ ]        |          0         |
    "gpu-tests",                        #     971    |      971       |    [ ]    |      [ ]        |          0         |
    "ml-darwin-aarch64-mps",            #    2351    |     1720       |    [x]    |      [ ]        |          0         |
    "ml-linux-x86_64-cpu",              #    5204    |     4216       |    [x]    |      [ ]        |          0         |
    "ml-linux-x86_64-cuda",             #    5331    |     4317       |    [x]    |      [ ]        |          0         |
    "ml-linux-x86_64-rocm",             #    2691    |     2570       |    [ ]    |      [ ]        |          0         |
    "radiuss-aws-aarch64",              #    1038    |      780       |    [x]    |      [ ]        |          0         |
    "radiuss-aws",                      #     594    |      444       |    [x]    |      [ ]        |          0         |
    "radiuss",                          #    2544    |     2028       |    [x]    |      [ ]        |          0         |
    "tutorial",                         #    1338    |     1065       |    [x]    |      [ ]        |          0         |
]

class BuiltSpec:
    def __init__(self, meta=None, archive=None):
        self.meta = meta
        self.archive = archive


################################################################################
#
def process_files(full_path):
    all_stack_specs = {}
    top_level_specs = {}

    find_built_specs(full_path, all_stack_specs, top_level_specs)

    missing_by_stack = {}

    for stack, stack_specs in all_stack_specs.items():
        for hash, built_spec in stack_specs.items():
            if hash not in top_level_specs:
                missing_at_top = find_or_add(stack, missing_by_stack, dict)
                missing_at_top[hash] = built_spec

    total_missing_at_top = 0

    print(f"Summary of specs missing from the top-level, by stack")
    for stack, missing_at_top in missing_by_stack.items():
        stack_specs = all_stack_specs[stack]
        stack_missings = len(missing_at_top)
        total_missing_at_top += stack_missings
        print(f"{stack}")
        print(f"    {len(stack_specs)} total, {stack_missings} missing from top")
        incomplete_pairs = 0
        for hash, built_spec in missing_at_top.items():
            print(f"        hash: {hash}")
            if built_spec.meta and built_spec.archive:
                # pass
                print(f"            {built_spec.meta}")
                print(f"            {built_spec.archive}")
            else:
                incomplete_pairs += 1
        print(f"    {incomplete_pairs} from stack are missing either meta or archive")

    print(f"Total: {total_missing_at_top} missing from the top")


################################################################################
#                    Regexes for the function below
TOP_LEVEL_META_REGEX =    re.compile(r"develop/build_cache/.+-([^\.]+).spec.json.sig$")
TOP_LEVEL_ARCHIVE_REGEX = re.compile(r"develop/build_cache/.+-([^\.]+).spack$")
STACK_META_REGEX =        re.compile(r"develop/([^/]+)/.+-([^\.]+).spec.json.sig$")
STACK_ARCHIVE_REGEX =     re.compile(r"develop/([^/]+)/.+-([^\.]+).spack$")


################################################################################
# Read the file and populate stack_specs and top_level_specs
#
#     top_level_specs = {
#         <hash>: <BuiltSpec>,
#         ...
#     }
#
#     stack_specs = {
#         <stack>: {
#             <hash>: <BuiltSpec>,
#             ...
#         },
#         ...
#     }
#
def find_built_specs(full_path, stack_specs, top_level_specs):
    with open(full_path) as f:
        for line in f:
            m = TOP_LEVEL_META_REGEX.search(line)
            if m:
                hash = m.group(1)
                spec = find_or_add(hash, top_level_specs, BuiltSpec)
                spec.meta = m.group(0)
                continue

            m = TOP_LEVEL_ARCHIVE_REGEX.search(line)
            if m:
                hash = m.group(1)
                spec = find_or_add(hash, top_level_specs, BuiltSpec)
                spec.archive = m.group(0)
                continue

            # Now we've ruled out its a top level spec

            m = STACK_META_REGEX.search(line)
            if m:
                stack = m.group(1)
                if stack not in STACKS_TO_EXCLUDE:
                    stack_dict = find_or_add(stack, stack_specs, dict)
                    hash = m.group(2)
                    spec = find_or_add(hash, stack_dict, BuiltSpec)
                    spec.meta = m.group(0)
                continue

            m = STACK_ARCHIVE_REGEX.search(line)
            if m:
                stack = m.group(1)
                if stack not in STACKS_TO_EXCLUDE:
                    stack_dict = find_or_add(stack, stack_specs, dict)
                    hash = m.group(2)
                    spec = find_or_add(hash, stack_dict, BuiltSpec)
                    spec.archive = m.group(0)
                continue

            # else it must be a public key, an index, or a hash of an index


################################################################################
#
def find_or_add(key, d, ctor):
    if key not in d:
        d[key] = ctor()
    return d[key]


################################################################################
#
def main():
    parser = argparse.ArgumentParser(
        prog="find_missing",
        description="Find specs in stacks missing from the root")

    parser.add_argument("--full", default=None, help="Abs path to full listing")

    args = parser.parse_args()

    process_files(args.full)


if __name__ == "__main__":
    main()

