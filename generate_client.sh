#!/usr/bin/env bash

# Generate Python client SDK from OpenAPI 3.0.0 spec


function run() {
    check_prerequisites

    # GENERATE SYNTHETICS
    synthetics_package="generated.synthetics_http_client.synthetics"
    synthetics_spec="synthetics.openapi.yaml"

    synthetics_client_output_dir="" # empty value -> will reflect synthetics_package

    generate_golang_client_from_openapi3_spec "$synthetics_spec" "$synthetics_package" "$synthetics_client_output_dir"
    change_ownership_to_current_user "generated"
}


function stage() {
    BOLD_BLUE="\e[1m\e[34m"
    RESET="\e[0m"
    msg="$1"

    echo
    echo -e "$BOLD_BLUE$msg$RESET"
}

function check_prerequisites() {
    stage "Checking prerequisites"

    if ! docker --version > /dev/null 2>&1; then
        echo "You need to install docker to run the generator"
        exit 1
    fi

    echo "Done"
}

function generate_golang_client_from_openapi3_spec() {
    stage "Generating golang client from openapi spec"

    spec_file="$1"
    package="$2"
    output_dir="$3"

    docker run --rm  -v "$(pwd):/local" \
        openapitools/openapi-generator-cli generate  \
        -i "/local/$spec_file" \
        -g python \
        --package-name "$package" \
        --additional-properties generateSourceCodeOnly=true \
        -o "/local/$output_dir"

    echo "Done"
}

function change_ownership_to_current_user() {
    dir="$1"
    stage "Changing ownership of $dir to $USER"

    sudo chown -R "$USER" "$dir" # by default the generated output is in user:group root:root

    echo "Done"
}

run
