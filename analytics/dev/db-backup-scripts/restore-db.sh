#!/usr/bin/env bash

set -e

export PGUSER=postgres
export PGPORT=5432
export PGHOST=localhost
export PGDATABASE=django
export PGPASSWORD=postgres


function load_from_file {
    local backup_file=$1

    echo "-------------------------------------------"
    table_name=$(echo $backup_file | rev | cut -d '/' -f 1 | rev | cut -d "." -f 1 | cut -d "_" -f 1,2)
    echo "Dropping existing rows from $table_name ..."
    psql -c "TRUNCATE TABLE $table_name CASCADE"

    HEADERS=$(head -n 1 $backup_file)
    echo "loading $table_name from $backup_file ..."
    psql -c "\copy $table_name($HEADERS) FROM '$backup_file' WITH(FORMAT CSV, HEADER, NULL '<null>')"
    # Fix the ID sequence after COPY FROM, if it exists.
    # This has to be wrapped in an anonymous function to work around errors if the sequence does not exist.
    seq_table_name=${table_name}_id_seq
    psql -c "
        DO
        \$$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_class where relname = '$seq_table_name') THEN
                PERFORM setval('$seq_table_name', max(id)) FROM ${table_name};
            END IF;
        END;
        \$$
        LANGUAGE plpgsql;
    "
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


# Since we don't import all job fact rows, delete any dimension rows that are
# not referenced by existing job fact rows, to ensure consistency.

# Step 1: Discover FK relationships where core_jobfact is the referencing table.
# Each row is: dim_table,dim_pk_col,jobfact_fk_col
echo "Discovering FK relationships for core_jobfact..."
readarray -t FK_RELATIONSHIPS < <(psql -t -A -F ',' -c "
    SELECT
        ccu.table_name  AS dim_table,
        ccu.column_name AS dim_pk_col,
        kcu.column_name AS jobfact_fk_col
    FROM information_schema.referential_constraints rc
    JOIN information_schema.key_column_usage kcu
        ON  kcu.constraint_name = rc.constraint_name
        AND kcu.table_schema    = rc.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
        ON  ccu.constraint_name = rc.unique_constraint_name
        AND ccu.table_schema    = rc.unique_constraint_schema
    WHERE kcu.table_name = 'core_jobfact'
")

# Step 2: Delete orphaned dimension rows using the discovered relationships.
echo "Deleting orphaned dimension rows..."
for relationship in "${FK_RELATIONSHIPS[@]}"
do
    IFS=',' read -r dim_table dim_pk_col jobfact_fk_col <<< "$relationship"
    echo "  Cleaning $dim_table ($dim_pk_col not in core_jobfact.$jobfact_fk_col)..."
    psql -c "
        DELETE FROM \"$dim_table\"
        WHERE NOT EXISTS (
            SELECT 1 FROM \"core_jobfact\"
            WHERE \"core_jobfact\".\"$jobfact_fk_col\" = \"$dim_table\".\"$dim_pk_col\"
        )
    "
done
