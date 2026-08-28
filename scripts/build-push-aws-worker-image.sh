#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <repository-uri> [tag] [model-directory]" >&2
}

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
repository_uri="${1}"
tag="${2:-ml-v1}"
model_directory="${3:-$(cd -- "${project_root}/.." && pwd)/PacificBioArchive}"
context_path="${project_root}/build/aws-worker-image"
dockerfile_directory="${project_root}/deployment/aws-worker"

if [[ ! "${repository_uri}" =~ ^([0-9]{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com/(.+)$ ]]; then
  echo "Invalid ECR repository URI: ${repository_uri}" >&2
  exit 2
fi
account_id="${BASH_REMATCH[1]}"
aws_region="${BASH_REMATCH[2]}"
repository_name="${BASH_REMATCH[3]}"
registry_host="${account_id}.dkr.ecr.${aws_region}.amazonaws.com"

current_account="$(aws sts get-caller-identity --query Account --output text)"
if [[ "${current_account}" != "${account_id}" ]]; then
  echo "AWS CLI is using account ${current_account}, but the ECR repository belongs to ${account_id}." >&2
  exit 1
fi

aws ecr describe-repositories \
  --region "${aws_region}" \
  --registry-id "${account_id}" \
  --repository-names "${repository_name}" \
  --output json >/dev/null

aws ecr get-login-password --region "${aws_region}" | \
  docker login --username AWS --password-stdin "${registry_host}"

for name in mdv5a.pt model.pt labels.txt; do
  if [[ ! -f "${model_directory}/${name}" ]]; then
    echo "Missing model artifact: ${model_directory}/${name}" >&2
    exit 1
  fi
done

rm -rf -- "${context_path}"
mkdir -p -- "${context_path}/models"
cp -R -- "${project_root}/backend" "${context_path}/backend"
cp -- "${project_root}/worker_adapter.py" "${context_path}/worker_adapter.py"
cp -- "${dockerfile_directory}/Dockerfile" "${context_path}/Dockerfile"
cp -- "${dockerfile_directory}/requirements-worker-container.txt" "${context_path}/requirements-worker-container.txt"
for name in mdv5a.pt model.pt labels.txt; do
  cp -- "${model_directory}/${name}" "${context_path}/models/${name}"
done

image="${repository_uri}:${tag}"
docker buildx build \
  --progress=plain \
  --platform linux/amd64 \
  --provenance=false \
  --push \
  --tag "${image}" \
  "${context_path}"

digest="$(aws ecr describe-images \
  --region "${aws_region}" \
  --registry-id "${account_id}" \
  --repository-name "${repository_name}" \
  --image-ids "imageTag=${tag}" \
  --query 'imageDetails[0].imageDigest' \
  --output text)"

if [[ ! "${digest}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo "Unable to resolve the pushed ECR image digest" >&2
  exit 1
fi

echo "Worker image URI: ${repository_uri}@${digest}"
