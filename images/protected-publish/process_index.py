import json

with open("./index_2024-04-29T08-29-50.json") as f:
    index_data = json.load(f)


installs = index_data["database"]["installs"]

total_count = 0
missing_count = 0

for hash, spec_obj in installs.items():
    if not spec_obj["in_buildcache"]:
        missing_count += 1

    total_count += 1

present_count = total_count - missing_count

print(f"There are {total_count} specs in the index, but {present_count} are present, and {missing_count} are missing")
