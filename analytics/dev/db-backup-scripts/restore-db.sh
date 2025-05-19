#!/usr/bin/env bash

export PGUSER=postgres
export PGPORT=5432
export PGHOST=localhost
export PGDATABASE=django
export PGPASSWORD=postgres

NULL_VALUE="<null>"


function load_from_file {
    local backup_file=$1

    echo "-------------------------------------------"
    table_name=$(echo $backup_file | rev | cut -d '/' -f 1 | rev | cut -d "." -f 1 | cut -d "_" -f 1,2)
    echo "Dropping existing rows from $table_name ..."
    psql -c "TRUNCATE TABLE $table_name CASCADE"

    HEADERS=$(head -n 1 $backup_file)
    echo "loading $table_name from $backup_file ..."
    psql -c "\copy $table_name($HEADERS) FROM '$backup_file' WITH(FORMAT CSV, HEADER, NULL '<null>')"
}


# Restore dimensional tables before fact tables,
# to ensure foreign keys are added correctly

echo "Restoring dimensional tables ..."
for backup_file in ./dumps/*dimension.csv
do
    load_from_file $backup_file
done

echo "Restoring fact tables ..."
for backup_file in ./dumps/*fact*.csv
do
    load_from_file $backup_file
done
