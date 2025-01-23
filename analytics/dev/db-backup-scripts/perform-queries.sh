#!/usr/bin/env bash

export PGUSER=postgres
export PGPORT=9999
export PGHOST=localhost
export PGDATABASE=analytics
export PGPASSWORD=$REMOTE_PGPASSWORD

# Fact tables and time limits
declare -A FACT_TABLES_TO_DAYS=(
    ["core_jobfact"]=90
    ["core_timerfact"]=30
    ["core_timerphasefact"]=7
)
declare -A FACT_TABLES_TO_DATE_FIELD=(
    ["core_jobfact"]="start_date_id"
    ["core_timerfact"]="date_id"
    ["core_timerphasefact"]="date_id"
)

function join_by {
  local d=${1-} f=${2-}
  if shift 2; then
    printf %s "$f" "${@/#/$d}"
  fi
}


# Query options
NULL_VALUE="<null>"

# Export dimension tables
DIMENSION_TABLES=$(psql -t -c "SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND table_name LIKE 'core_%dimension'")
for dimension_table in $DIMENSION_TABLES
do
    echo "Querying $dimension_table..."
    COLUMNS=$(psql -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = '$dimension_table' AND is_generated = 'NEVER'")
    JOINED_COLUMNS=$(join_by , $COLUMNS)
    psql --pset="null=$NULL_VALUE" --csv -c "SELECT $JOINED_COLUMNS FROM $dimension_table" -o "dumps/$dimension_table.csv"
done


# Export fact tables
for fact_table in ${!FACT_TABLES_TO_DAYS[@]}
do
    echo "Querying $fact_table..."

    FACT_TABLE_COLUMNS=$(psql -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = '$fact_table' AND is_generated = 'NEVER'")
    JOINED_COLUMNS=$(join_by , $FACT_TABLE_COLUMNS)

    DAY_LIMIT=${FACT_TABLES_TO_DAYS[$fact_table]}
    DATE_FIELD=${FACT_TABLES_TO_DATE_FIELD[$fact_table]}
    psql --pset="null=$NULL_VALUE" --csv \
        -o "dumps/${fact_table}_last_${DAY_LIMIT}_days.csv" \
        -c "SELECT $JOINED_COLUMNS FROM $fact_table \
            LEFT JOIN core_datedimension ON $fact_table.$DATE_FIELD = core_datedimension.date_key \
            WHERE date >= CAST((NOW() + INTERVAL '-$DAY_LIMIT day') AS date)"
done
