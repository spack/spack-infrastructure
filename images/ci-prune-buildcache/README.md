# Binary Cache Mirror Pruner


The motivation for developing pruning strategies for Spack build caches is to control the sizes of build caches to support faster searchability by CI pipelines and downstream users using the public mirrors. With the rapidly increasing volume of domain specific stacks and unique packages specs being built on a daily basis, Spack's public build caches have exceeded a critical mass leading to noticeable overhead to simply search the build cache for usable binaries.

## Determine Keep Hashes

The first step to pruning is to determine which stacks are active and require pruning, and for those stacks which hashes are required to be kept. For the pruning of the Spack public binaries, the method chosen was to look at all of the pipelines run in the past 14 days and collect the `spack.lock` artifacts from all of the generate jobs for each stack. From the `spack.lock` files, the list of concretized hashes is aggregated across each stack for all of the pipelines. In addition, all of the hashes for all of the pipelines are aggregated in a list for the "Global" or "Top Level" mirror.

```
{
...
  "e4s": ["aaaabbbbccccddddeeeeffffgggghhhh", "00001111222233334444555566666666", ...]
...
  "_global": ["aaaabbbbccccddddeeeeffffgggghhhh", "00001111222233334444555566666666", ...]
}
```

There are other methods that could be used for generating the keep list, but this one was chosen as it is relatively simple. Additional methods could also be employed such as a strictly date based approach that sought only to keep the binaries that were newer than a certain date, but it this is deceptively simple as it is almost guaranteed to invalidate existing binaries in the stack by removing their dependencies. While there is a work around for that problem, like traversing up the graph for each pruned spec to find all of the dependents, it becomes an extremely aggressive strategy. The resulting problem then becomes currently running pipelines and installations by external users would begin to fail unexpectedly as cached binaries began to disappear out from under them.

## Pruning

Three methods were investigated and implemented for pruning of Spack build caches.

* Direct (greedy) Pruning
* Index Based Pruning
* Orphan Pruning

Direct and Index based pruning both require the specification of the "Keep Hashes" list noted previously. The main difference between these two methods is what is considered when doing the pruning.

Orphan pruning refers to pruning hashes in the mirror that only have a meta-data (.spec/.spec.json/.spec.json.sig) file or binary file (.spack/.tar.gz) but not both. In the case of the orphaned binaries there is no real harm other than wasted storage space. However, orphaned meta-data files can lead to invalid build cache indexes and cause Spack to think there is a binary available when in reality there is none. The result of this is Spack crashing on a bad request for users when it could have done something different like rebuild the pacakge or error that no binary could be found for a spec.


### Direct Pruning


Direct pruning is a strategy that goes directly to the contents of the mirror to determine the hashes that can be pruned. It is similar to the Orphan pruning method in this way, and will detect and prune orphaned binaries but not orphaned spec files.

The inputs to "Direct Pruning" is a "keep list" (set `K`) of hashes and a start date to begin considering binaries for pruning from.

1. List all of the binary files older than a specified start date and extract their hashes. (set `B`)
2. Compute the prunable hashes as `B` - `K`. (set `P`)
3. Prune all of the files in the build cache that have hash in prunable set `P`.

This is a very simple method and does not require downloading any of the objects from S3. The main weakness in this method is that it relies on a user provided date as the pruning threshold. This method doesn't really suffer from this weakness in practice though as it is known that the threshold date used for pruning is sufficiently j

### Index Based Pruning

Index based pruning uses the binary cache index file to determine what hashes are available in the mirror to prune and ignores date stamps or any other metrics on the binaries or meta-files themselves. The assumption there is that the index provides a full view of the build cache as is available for pruning. This is the same assumption utilitized by the Orphan Pruning method.

The only input to "Index Based Pruning" is a "keep list" (set `K`) of hashes.

1. Fetch and load the `index.json` from the build cache and extract the hashes that are "in the build cache". (set `I`)
2. Compute the prunable hashes as `I` - `K`. (set `P`)
3. Prune all of the files in the build cache that have hash in prunable set `P`.

This method has an advantage in that it only prunes things that are consistent with the current state of the build cache. This avoids some of the subtle issues associated with pruning orphans implicitly.

### Orphan Pruning

In the process of comparing the Direct and Index pruning methods it became clear there were edge cases where meta files and binaries were being orphaned in build caches. The reason for this could be anything from manual deletion not deleting the correct pair, or the pruning deletion script failing to delete some files. In either case, this leaves the build cache in an inconsistent state which also needs to be corrected.

Orphan Pruning provides a guaranteed "safe" method of pruning both binaries and meta-files. As a result it is also the most complicated pruning method listed here.

1. Fetch the `index.json` from the build cache.
2. Extract the hashes from the `index.json` (set `I`)
3. Clip the provided cut-off date with the last modified date of the `index.json` file [^1].
4. List the meta-files found in the build cache and extract their hashes. (set `M`)
5. Compute the intersection of `M` and `I` as the subset of meta-files that could be orphaned. (set `S`)
6. List the binary files found in the build cache older than the cut-off date extract their hashes.  (set `B`)
7. Compute the orphaned meta-file hashes as `S` - `B` and append to prunable hashes. (set `P`)
8. Compute the orphaned binary file hashes as `B` - `M` and append to prunable hashes. (set `P`).
9. Prune all of the files in the build cache that have hash in prunable set `P`.


[^1]: Using the date stamp on the build cache's `index.json` as the cutoff date for orphaned binary pruning vs a manually provided date stamp, it is guaranteed that the binaries older than that date should have had a meta-file uploaded and considered in the index at some point in the build cache life cycle. Binaries that exist later than then index's modification date are potentially unmatched due to mate-files not having been uploaded yet, which are not orphaned but they may appear to be. This is generally not a problem in practice, but it is an important consideration when dealing with orphan pruning.


## Summary

For production pruning of the Spack public mirrors Direct and Orphan pruning were determined to be the most useful pruning methods as they sufficiently prune binaries without risk of over pruning. The general workflow that should be followed for pruning is to first prune Orphaned objects, and then apply "Direct pruning".
