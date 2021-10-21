#!/usr/bin/env bash

# Generate Python client SDK from OpenAPI 3.0.0 spec

function run() {
    check_prerequisites

    # GENERATE SYNTHETICS
    synthetics_package="generated.synthetics_http_client.synthetics"
    source_url="https://raw.githubusercontent.com/kentik/api-schema-public/master/gen/openapiv2/kentik/synthetics/v202101beta1/synthetics.swagger.json"

    generate_python_client_from_openapi2_spec "${source_url}" "${synthetics_package}"
}

function stage() {
    if [ "${BASH_VERSION%%.*}" -lt 5 ]; then
        BOLD_BLUE="======= "
        RESET=""
    else
        BOLD_BLUE="\e[1m\e[34m"
        RESET="\e[0m"
    fi
    msg="$1"

    echo
    echo -e "$BOLD_BLUE$msg$RESET"
}

function check_prerequisites() {
    stage "Checking prerequisites"

    if ! docker --version >/dev/null 2>&1; then
        echo "You need to install docker to run the generator"
        fail=1
    fi

    if [ -z "$(which curl)" ]; then
        echo "Need 'curl' to fetch and convert OpenAPI spec"
        fail=1
    fi

    if [ ${fail} ]; then
        exit 1
    fi
    echo "Done"
}

function generate_python_client_from_openapi2_spec() {
    spec_url="$1"
    package="$2"
    output_dir=${package//"."/"/"}
    top_dir=${output_dir%%/*}

    # convert OpenAPIv2 spec to OpenAPIv3 in YAML format
    stage "Fetching and converting OpenAPI spec"
    spec_file=${top_dir}/synthetics.openapi.yaml
    curl --silent "https://converter.swagger.io/api/convert?url=${spec_url}" \
        -H "Accept: application/yaml" -o "${spec_file}"

    stage "Cleaning up '${top_dir}'"
    rm -rf "${output_dir}"
    rm -rf "${top_dir}"/__pycache__
    mkdir -p "${output_dir}" # create the output directory to avoid the need to change permissions later

    stage "Generating Python client from openapi spec"
    docker run --rm -v "$(pwd):/local" \
        openapitools/openapi-generator-cli generate \
        -i "/local/${spec_file}" \
        -g python \
        --package-name "$package" \
        --additional-properties generateSourceCodeOnly=true \
        -o "/local/"

    echo "Done"
}

run
