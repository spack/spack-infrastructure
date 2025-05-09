## What is this?

These scripts allow population of the local database with real data from the prod analytics database. This is useful for testing changes to the analytics app. These scripts have the following functions:

1. `analytics-db-proxy.sh` - This script spins up a pod within the cluster that bounces all traffic pointed at `localhost:9999` to the analytics database (specified by the `REMOTE_DB_HOST` env var). This is necessary as the database is behind an AWS VPC, so it's inaccessible outside of the cluster.
2. `perform-queries.sh` - This script dumps data from the dimensional and fact tables to CSV files in the `dumps/` directory.
3. `restore-db.sh` - This script populates data into the database from the files in the `dumps/` directory. **Note**, this will delete any existing rows in any of the tables that data is populated into, to avoid conflicts.

## Requirements

For the `analytics-db-proxy.sh` script, the `$REMOTE_DB_HOST` env var must be set to the hostname of the AWS RDS instance. This can be found in the AWS console. You must also ensure you have cluster access, and that your `KUBECONFIG` file is properly set, to allow for the cluster proxy to work.

For the `perform-queries.sh` script, the `REMOTE_PGPASSWORD` env var must be set to the password of the `postgres` user to the prod analytics database.
