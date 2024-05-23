#!/usr/bin/env spack-python

# copy of https://github.com/sandialabs/spack-manager/blob/main/manager/manager_cmds/cache_query.py
# as a stand alone script
# query the buildcache like `spack find`

import argparse

import spack.binary_distribution as bindist
import spack.cmd as cmd
import spack.cmd.find


parser = argparse.ArgumentParser()
spack.cmd.find.setup_parser(parser)

def cache_search(self, **kwargs):
    qspecs = spack.cmd.parse_specs(self.values)
    search_engine = bindist.BinaryCacheQuery(True)
    results = {}
    for q in qspecs:
        hits = search_engine(str(q), **kwargs)
        for hit in hits:
            results[hit.dag_hash()] = hit
    return sorted(results.values())

spack.cmd.common.arguments.ConstraintAction._specs = cache_search

def find(parser, args):
    spack.cmd.find.find(parser, args)

if __name__ == "__main__":
    args = parser.parse_args()
    find(parser, args)

