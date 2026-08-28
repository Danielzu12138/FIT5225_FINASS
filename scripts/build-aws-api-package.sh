#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
output_path="${1:-${project_root}/build/aws-api.zip}"
stage_path="${project_root}/build/aws-api-stage"
python_bin="${project_root}/.venv/bin/python"

if [[ ! -x "${python_bin}" ]]; then
  echo "Missing Python virtual environment: ${python_bin}" >&2
  echo "Create it with: python3.12 -m venv ${project_root}/.venv" >&2
  exit 1
fi

certifi_path="$(${python_bin} -c 'import certifi; print(certifi.where())')"

rm -rf -- "${stage_path}"
mkdir -p -- "${stage_path}" "$(dirname -- "${output_path}")"

"${python_bin}" -m pip install \
  --disable-pip-version-check \
  --ignore-installed \
  --no-compile \
  --only-binary=:all: \
  --cert "${certifi_path}" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 312 \
  --require-hashes \
  --requirement "${project_root}/backend/aws_api/requirements-lambda.lock" \
  --target "${stage_path}"

"${python_bin}" -m pip install \
  --disable-pip-version-check \
  --ignore-installed \
  --no-compile \
  --only-binary=:all: \
  --cert "${certifi_path}" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 312 \
  --requirement "${project_root}/backend/aws_api/requirements-lambda-cloud.txt" \
  --target "${stage_path}"

cp -R -- "${project_root}/backend" "${stage_path}/backend"
cp -R -- "${project_root}/contracts" "${stage_path}/contracts"
cp -- "${project_root}/backend/aws_api/lambda_adapter.py" "${stage_path}/lambda_adapter.py"
cp -- "${project_root}/notification_adapter.py" "${stage_path}/notification_adapter.py"

rm -f -- "${output_path}"
(
  cd -- "${stage_path}"
  zip -qr "${output_path}" .
)

echo "AWS API package: ${output_path} (backend.aws_api.app:app)"
