#!/usr/bin/env bash

export PGUSER=postgres
export PGPORT=9999
export PGHOST=localhost
export PGDATABASE=analytics
export PGPASSWORD=$REMOTE_PGPASSWORD


declare -A TABLE_ARGS

# Process arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -t|--table)
      # TABLE_ARG="$2"
      TABLE_ARGS[$2]=1
      shift # past argument
      shift # past value
      ;;
    -*|--*)
      echo "Unknown option $1"
      exit 1
      ;;
    *)
      POSITIONAL_ARGS+=("$1") # save positional arg
      shift # past argument
      ;;
  esac
done


# Fact tables and time limits
declare -A FACT_TABLES_TO_DAYS=(
    ["core_jobfact"]=1000
    ["core_timerfact"]=30
    ["core_timerphasefact"]=7
)
declare -A FACT_TABLES_TO_DATE_FIELD=(
    ["core_jobfact"]="start_date_id"
    ["core_timerfact"]="date_id"
    ["core_timerphasefact"]="date_id"
)
declare -A FACT_TABLES_TO_TIME_FIELD=(
    ["core_jobfact"]="start_time_id"
    ["core_timerfact"]="time_id"
    ["core_timerphasefact"]="time_id"
)

function join_by {
  local d=${1-} f=${2-}
  if shift 2; then
    printf %s "$f" "${@/#/$d}"
  fi
}

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
DUMPS_DIR="${SCRIPT_DIR}/dumps"

# Ensure dumps directory exists
if [ ! -d $DUMPS_DIR ]; then
  mkdir $DUMPS_DIR
fi


# Ensure all retrieved records have a consistent end timestamp
LAST_RECORD_TIMESTAMP=$(psql -t -c "select NOW() + INTERVAL '-1 hour' as timestamp")

# Query options
NULL_VALUE="<null>"

# Export dimension tables
DIMENSION_TABLES=$(psql -t -c "SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND table_name LIKE 'core_%dimension'")
for dimension_table in $DIMENSION_TABLES
do
    # Skip if table arg supplied and this table name does not match
    [ "${#TABLE_ARGS[@]}" -eq 0 ] || [ "${TABLE_ARGS[$dimension_table]}" ] || continue

    echo "Querying $dimension_table..."
    COLUMNS=$(psql -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = '$dimension_table' AND is_generated = 'NEVER'")
    JOINED_COLUMNS=$(join_by , $COLUMNS)
    psql --pset="null=$NULL_VALUE" --csv -c "SELECT $JOINED_COLUMNS FROM $dimension_table" -o "$DUMPS_DIR/$dimension_table.csv"
done


# Export fact tables
for fact_table in ${!FACT_TABLES_TO_DAYS[@]}
do
    # Skip if table arg supplied and this table name does not match
    [ "${#TABLE_ARGS[@]}" -eq 0 ] || [ "${TABLE_ARGS[$fact_table]}" ] || continue

    echo "Querying $fact_table..."

    FACT_TABLE_COLUMNS=$(psql -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = '$fact_table' AND is_generated = 'NEVER'")
    JOINED_COLUMNS=$(join_by , $FACT_TABLE_COLUMNS)

    DAY_LIMIT=${FACT_TABLES_TO_DAYS[$fact_table]}
    DATE_FIELD=${FACT_TABLES_TO_DATE_FIELD[$fact_table]}
    TIME_FIELD=${FACT_TABLES_TO_TIME_FIELD[$fact_table]}
    psql --pset="null=$NULL_VALUE" --csv \
        -o "$DUMPS_DIR/${fact_table}_last_${DAY_LIMIT}_days.csv" \
        -c "SELECT $JOINED_COLUMNS FROM $fact_table \
            LEFT JOIN core_datedimension dd ON $fact_table.$DATE_FIELD = dd.date_key \
            LEFT JOIN core_timedimension td ON $fact_table.$TIME_FIELD = td.time_key \
            WHERE \
              date >= CAST((NOW() + INTERVAL '-$DAY_LIMIT day') as date) \
              AND CAST((dd.date + td.time) as timestamp) < '$LAST_RECORD_TIMESTAMP' \
            "
done
