from __future__ import annotations

import re
from pathlib import Path

import hcl2


ROOT = Path(__file__).resolve().parents[2]


def read_stack(cloud: str) -> str:
    files = sorted((ROOT / "infra" / cloud).glob("*.tf"))
    assert files, f"missing {cloud} Terraform stack"
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_aws_stack_contains_required_serverless_resources() -> None:
    stack = read_stack("aws")
    required = (
        "aws_cognito_user_pool",
        "aws_cognito_user_pool_client",
        "aws_apigatewayv2_api",
        "aws_apigatewayv2_authorizer",
        "aws_s3_bucket_public_access_block",
        "aws_s3_bucket_server_side_encryption_configuration",
        "aws_lambda_function",
        "aws_sqs_queue",
        "aws_cloudwatch_event_bus",
        "aws_sns_topic",
        "aws_secretsmanager_secret",
        "aws_cloudwatch_log_group",
    )
    for resource in required:
        assert resource in stack, resource
    assert "block_public_acls       = true" in stack
    assert 'authorization_type = "JWT"' in stack


def test_azure_stack_contains_required_data_and_function_resources() -> None:
    stack = read_stack("azure")
    required = (
        "azurerm_resource_group",
        "azurerm_linux_function_app",
        "azurerm_cosmosdb_account",
        "azurerm_cosmosdb_sql_database",
        "azurerm_cosmosdb_sql_container",
        "azurerm_key_vault",
        "azurerm_application_insights",
        "azurerm_role_assignment",
    )
    for resource in required:
        assert resource in stack, resource
    assert re.search(r'partition_key_paths\s*=\s*\["/owner_sub"\]', stack)


def test_cloud_stacks_do_not_embed_credentials() -> None:
    combined = read_stack("aws") + read_stack("azure")
    forbidden = ("AKIA", "client_secret = \"", "access_key = \"", "password = \"")
    for marker in forbidden:
        assert marker not in combined


def test_every_terraform_file_parses_as_hcl() -> None:
    for path in sorted((ROOT / "infra").glob("**/*.tf")):
        with path.open(encoding="utf-8") as stream:
            parsed = hcl2.load(stream)
        assert isinstance(parsed, dict), path


def test_aws_api_package_uses_the_real_asgi_entrypoint_and_exposes_required_outputs() -> None:
    stack = read_stack("aws")
    outputs = (ROOT / "infra" / "aws" / "outputs.tf").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build-aws-api-package.ps1").read_text(encoding="utf-8")

    assert "lambda_stub" not in stack
    assert 'handler          = "lambda_adapter.handler"' in stack
    assert "api_package_path" in stack
    assert "backend.aws_api.app:app" in build_script
    assert "requirements-lambda.lock" in build_script
    assert "--require-hashes" in build_script
    for output in ("api_base_url", "cognito_user_pool_id", "cognito_app_client_id", "notification_topic_arn"):
        assert f'output "{output}"' in outputs
    for route in (
        "GET /media",
        "GET /subscriptions",
        "PUT /subscriptions/{subscription_id}",
        "DELETE /subscriptions/{subscription_id}",
    ):
        assert f'"{route}"' in stack
    assert '"GET /media"' in stack


def test_aws_environment_and_cors_match_application_runtime_values() -> None:
    main = (ROOT / "infra" / "aws" / "main.tf").read_text(encoding="utf-8")
    variables = (ROOT / "infra" / "aws" / "variables.tf").read_text(encoding="utf-8")

    assert re.search(r'variable\s+"environment"\s*\{.*?default\s*=\s*"development"', variables, re.DOTALL)
    for value in ("local", "test", "development", "production"):
        assert f'"{value}"' in variables
    assert 'allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]' in main


def test_task5_protects_the_composed_media_list_route() -> None:
    main = (ROOT / "infra" / "aws" / "main.tf").read_text(encoding="utf-8")

    protected_routes = re.search(r'protected_routes\s*=\s*toset\(\[(.*?)\]\)', main, re.DOTALL)
    assert protected_routes is not None
    assert '"GET /media"' in protected_routes.group(1)


def test_temporary_query_objects_are_available_to_api_and_worker() -> None:
    main = (ROOT / "infra" / "aws" / "main.tf").read_text(encoding="utf-8")

    # The API stages the reference file and the worker reads it (and may write
    # extracted video frames) before the temporary prefix is cleaned up.
    assert main.count('"${aws_s3_bucket.media.arn}/temporary-query/*"') >= 2


def test_obsolete_lambda_stub_is_rejected() -> None:
    assert not (ROOT / "infra" / "aws" / "lambda_stub").exists()


def test_infrastructure_validation_builds_the_api_package_before_static_or_terraform_checks() -> None:
    validator = (ROOT / "scripts" / "validate-infra.ps1").read_text(encoding="utf-8")

    assert "build-aws-api-package.ps1" in validator
    assert validator.index("build-aws-api-package.ps1") < validator.index("test_terraform_static.py")


def test_aws_api_package_build_targets_lambda_linux_python() -> None:
    build_script = (ROOT / "scripts" / "build-aws-api-package.ps1").read_text(encoding="utf-8")

    assert "--platform manylinux2014_x86_64" in build_script
    assert "--python-version 312" in build_script
    assert "--only-binary=:all:" in build_script
    assert "--ignore-installed" in build_script


def test_lambda_requirements_cover_imports_reached_by_the_runtime_entrypoint() -> None:
    requirements = (ROOT / "backend" / "aws_api" / "requirements-lambda.txt").read_text(encoding="utf-8")

    for distribution in (
        "fastapi==",
        "mangum==",
        "pydantic==",
        "pydantic-settings==",
        "PyJWT[crypto]==",
        "httpx==",
        "Pillow==",
        "python-multipart==",
    ):
        assert distribution in requirements


def test_lambda_lock_is_fully_resolved_and_hash_checked() -> None:
    lock_path = ROOT / "backend" / "aws_api" / "requirements-lambda.lock"
    assert lock_path.exists()
    logical_lines = lock_path.read_text(encoding="utf-8").replace("\\\n", " ").splitlines()
    locked: set[str] = set()
    for line in logical_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirement = stripped.split()[0]
        assert "==" in requirement, requirement
        assert "--hash=sha256:" in stripped, requirement
        locked.add(requirement.split("==", 1)[0].split("[", 1)[0].casefold())

    expected = {
        "annotated-types",
        "anyio",
        "certifi",
        "cffi",
        "cryptography",
        "fastapi",
        "h11",
        "httpcore",
        "httpx",
        "idna",
        "mangum",
        "pillow",
        "pydantic",
        "pydantic-core",
        "pydantic-settings",
        "pycparser",
        "pyjwt",
        "python-dotenv",
        "python-multipart",
        "starlette",
        "typing-extensions",
    }
    assert locked == expected
