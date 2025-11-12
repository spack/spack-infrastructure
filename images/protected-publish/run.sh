cmd=$1
shift

case "$cmd" in
  *pub*)
    py_cmd="pkg.publish";;
  *mig*)
    exec /srcs/migrate.sh;;
  *snap*)
    py_cmd="pkg.snapshot";;
  *val*)
    py_cmd="pkg.validate_index";;
  *)
    echo "Unknown command: $cmd"
    exit 1;;
esac

python -m $py_cmd $@
