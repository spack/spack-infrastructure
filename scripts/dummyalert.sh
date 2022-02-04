#!/bin/bash

if [[ -z "$CLIENT_CERT" ]]; then
    echo "Must provide CLIENT_CERT in environment" 1>&2
    exit 1
fi


if [[ -z "$CLIENT_KEY" ]]; then
    echo "Must provide CLIENT_KEY in environment" 1>&2
    exit 1
fi

name=DummyAlert-$RANDOM
url='https://alertmanager.spack.io/api/v1/alerts'
bold=$(tput bold)
normal=$(tput sgr0)

generate_post_data() {
  cat <<EOF
[{
  "status": "$1",
  "labels": {
    "alertname": "DummyAlert",
    "name": "${name}",
    "service": "my-service",
    "severity":"warning",
    "instance": "${name}.example.net",
    "namespace": "monitoring",
    "source_namespace": "custom"
  },
  "annotations": {
    "summary": "Dummy Alert",
    "description": "This is a dummy alert for ${name}.  Please Ignore."
  },
  "generatorURL": "http://nota.realdomain.com/$name"
  $2
  $3
}]
EOF
}

echo "${bold}Firing alert ${name} ${normal}"
printf -v startsAt ',"startsAt" : "%s"' $(date --rfc-3339=seconds | sed 's/ /T/')
POSTDATA=$(generate_post_data 'firing' "${startsAt}")
curl --cert $CLIENT_CERT --key $CLIENT_KEY $url --data "$POSTDATA" --trace-ascii /dev/stdout
echo -e "\n"

echo "${bold}Press enter to resolve alert ${name} ${normal}"
read

echo "${bold}Sending resolved ${normal}"
printf -v endsAt ',"endsAt" : "%s"' $(date --rfc-3339=seconds | sed 's/ /T/')
POSTDATA=$(generate_post_data 'firing' "${startsAt}" "${endsAt}")
curl --cert $CLIENT_CERT --key $CLIENT_KEY $url --data "$POSTDATA" --trace-ascii /dev/stdout
echo -e "\n"
