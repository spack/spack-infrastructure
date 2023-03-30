import upload_gitlab_failure_logs as taxonomy
import sys

if __name__ == "__main__":
    for trace_file in sys.argv:
        with open(trace_file) as trace:
            print(trace_file, ": ", taxonomy.classify(trace.read()))
