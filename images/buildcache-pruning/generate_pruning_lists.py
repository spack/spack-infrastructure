import argparse
import glob
import json
import os
import re


STACK_REGEX=re.compile(r"\s+develop/([^/]+)/build_cache")
METADATA_REGEX = re.compile(r"([^-]{32})\.spec\.json\.sig$")
ARCHIVE_REGEX = re.compile(r"([^-]{32})\.spack$")
S3_META_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\d+\s+(.+)$")


def a_not_in_b(a, b):
    """Given 2 lists, a and b, return all elements of a which are not in b"""
    return [ha for ha in a if ha not in b]


class StackMirrorInformation():
    def __init__(self):
        self.metadata_hashes= set()
        self.metadata_info = dict()
        self.archive_hashes = set()
        self.archive_info = dict()


def get_job_name_for_stack(stack_name):
    """Useful in case the generate job name doesn't match the stack name"""
    if stack_name == "deprecated":
        return "deprecated-ci"
    return stack_name


def process_bucket_listing(bucket_listing_path):
    """ Process the bucket listing and build up information about all of the
        stacks based on the contents of the mirror. """
    stack_information = dict()

    with open(bucket_listing_path) as f:
        for line in f:
            # Ignore lines that don't have to do with the stack of interest
            m = STACK_REGEX.search(line)
            if m:
                this_stack_name = m.group(1)
                if this_stack_name not in stack_information:
                    stack_information[this_stack_name] = StackMirrorInformation()

                info = stack_information[this_stack_name]
                metadata_hashes= info.metadata_hashes
                metadata_info = info.metadata_info
                archive_hashes = info.archive_hashes
                archive_info = info.archive_info

                # Is the line a spec file?
                m = METADATA_REGEX.search(line)
                if m:
                    metadata_hashes.add(m.group(1))
                    metadata_info[m.group(1)] = line

                # Is the line a binary archive?
                m = ARCHIVE_REGEX.search(line)
                if m:
                    archive_hashes.add(m.group(1))
                    archive_info[m.group(1)] = line

    return stack_information


def check_stack(stack_name, stack_info, lock_file_pattern, output_dir):
    """ Look in the information from the mirror for this stack to find unmatched
        files in the mirror (spec files with no archive or archives with no spec
        file).  Then compare the mirror information with the set of hashes found
        in all of the spack.lock files from the pipeline generation jobs that
        are associated with this stack, to create a list of urls we can prune
        from the mirror. """
    metadata_hashes = stack_info.metadata_hashes
    metadata_info = stack_info.metadata_info
    archive_hashes = stack_info.archive_hashes
    archive_info = stack_info.archive_info

    pipeline_job_name = get_job_name_for_stack(stack_name)
    lockfile_glob = lock_file_pattern.format(pipeline_job_name)

    ### Print information about any spec/spack mismatches (archives w/out metadata
    ### and metadata w/out archives)
    print(f"Processing stack: {stack_name}")

    print(f"  Found {len(metadata_hashes)} spec files")
    print(f"  Found {len(archive_hashes)} archive files")

    only_metafiles = a_not_in_b(metadata_hashes, archive_hashes)
    only_archives = a_not_in_b(archive_hashes, metadata_hashes)

    print(f"  There are {len(only_metafiles)} spec files without an archive:")

    if len(only_metafiles) > 0:
        relevant_lines = []
        for metahash in only_metafiles:
            relevant_lines.append(metadata_info[metahash].strip())

        output_path = os.path.join(output_dir, f"{stack_name}_unmatched_specfiles_meta.txt")
        with open(output_path, "w") as f:
            for line in sorted(relevant_lines):
                f.write(f"{line}\n")

        no_match = 0
        output_path = os.path.join(output_dir, f"{stack_name}_unmatched_specfiles_prunable.txt")
        with open(output_path, "w") as f:
            for line in sorted(relevant_lines):
                m = S3_META_REGEX.search(line)
                if m:
                    f.write(f"{m.group(1)}\n")
                else:
                    no_match += 1

        if no_match > 0:
            print(f"Could not match {no_match} lines when writing prunable (unmatched specfile urls")

    print(f"  There are {len(only_archives)} archives without metadata:")

    if len(only_archives) > 0:
        relevant_lines = []
        for archivehash in only_archives:
            relevant_lines.append(archive_info[archivehash].strip())

        output_path = os.path.join(output_dir, f"{stack_name}_unmatched_archives_meta.txt")
        with open(output_path, "w") as f:
            for line in sorted(relevant_lines):
                f.write(f"{line}\n")

        no_match = 0
        output_path = os.path.join(output_dir, f"{stack_name}_unmatched_archives_prunable.txt")
        with open(output_path, "w") as f:
            for line in sorted(relevant_lines):
                m = S3_META_REGEX.search(line)
                if m:
                    f.write(f"{m.group(1)}\n")
                else:
                    no_match += 1

        if no_match > 0:
            print(f"Could not match {no_match} lines when writing prunable (unmatched archive) urls")

    ### Generate the keep list for the stack by finding every hash generated in any
    ### pipeline in the time window (see get_pipelines.py for the code that fetches
    ### all the pipelines, downloads, and extracts the artifacts)
    file_list = glob.glob(lockfile_glob)
    stack_keep_hashes = set()

    print(f"  Generating keep list for {stack_name}")
    print(f"    There are {len(file_list)} {stack_name} lock files:")
    for file_path in file_list:
        with open(file_path) as f:
            lock_data = json.loads(f.read())

        spec_dict = lock_data["concrete_specs"]
        lock_hashes = spec_dict.keys()

        for h in lock_hashes:
            stack_keep_hashes.add(h)

    print(f"    Found {len(stack_keep_hashes)} keep hashes in the {stack_name} stack")

    ### Compare the data generated from the bucket listing in step 1 with the keep
    ### list generated in step 3, in order to generate the pruning list for the stack
    relevant_lines = []
    for hash in archive_hashes:
        if hash not in stack_keep_hashes:
            if hash in metadata_info:
                relevant_lines.append(metadata_info[hash].strip())
            if hash in archive_info:
                relevant_lines.append(archive_info[hash].strip())

    output_path = os.path.join(output_dir, f"{stack_name}_unused_recently_meta.txt")
    with open(output_path, "w") as f:
        for line in sorted(relevant_lines):
            f.write(f"{line}\n")

    no_match = 0
    output_path = os.path.join(output_dir, f"{stack_name}_unused_recently_prunable.txt")
    with open(output_path, "w") as f:
        for line in sorted(relevant_lines):
            m = S3_META_REGEX.search(line)
            if m:
                f.write(f"{m.group(1)}\n")
            else:
                no_match += 1

    if no_match > 0:
        print(f"Could not match {no_match} lines when writing prunable (recently unused) urls")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="""Generate pruning lists""")
    parser.add_argument("bucket_contents", type=str,
        help="Absolute path to file containing bucket contents (aws s3 ls --recursive <url>)")
    parser.add_argument("artifacts_dir", type=str,
        help="Absolute path to directory containing downloaded/extracted artifacts (generate jobs)")
    parser.add_argument("-o", "--output-dir", type=str, default=os.getcwd(),
        help="Directory to store generated pruning lists, default is current directory")
    args = parser.parse_args()

    lock_file_pattern = os.path.join(args.artifacts_dir, "**/**/{0}/jobs_scratch_dir/concrete_environment/spack.lock")
    stacks_information = process_bucket_listing(args.bucket_contents)

    for stack_name, stack_info in stacks_information.items():
        check_stack(stack_name, stack_info, lock_file_pattern, args.output_dir)
