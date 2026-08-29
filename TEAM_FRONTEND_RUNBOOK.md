# Pacific BioArchive 队友运行与测试指南

本文档用于队友在本地运行已部署的 Pacific BioArchive 前端，并验证现有 AWS/Azure 云端功能。

本指南默认使用已经部署好的开发环境，不执行 Terraform，不创建新的云资源。

## 1. 当前环境

| 项目 | 值 |
|---|---|
| AWS Region | `ap-southeast-2` |
| AWS Account | `983367475562` |
| AWS API | `https://j85cs8gf3d.execute-api.ap-southeast-2.amazonaws.com` |
| S3 Bucket | `pacific-bioarchive-development-media-983367475562` |
| API Lambda | `pacific-bioarchive-development-api` |
| Worker Lambda | `pacific-bioarchive-development-media-worker` |
| Azure Subscription | `6932a700-63c2-4df8-8964-c5e0e2b906e2` |
| Azure Resource Group | `pacific-bioarchive-development-rg-kr` |
| Azure Function | `pacific-bioarchive-development-data-pba826` |
| Azure Function URL | `https://pacific-bioarchive-development-data-pba826.azurewebsites.net` |
| Cognito User Pool | `ap-southeast-2_XQbfs4ef4` |
| Cognito App Client | `6fp1i37u3jtcoe9sggbe71uocn` |
| Cognito Domain | `https://pba826-group9.auth.ap-southeast-2.amazoncognito.com` |

## 2. 不要共享或提交的内容

以下内容不要放进 GitHub，也不要放进普通聊天或压缩包：

- AWS Secret Access Key、Azure 密码、MFA 验证码
- Cognito access token、refresh token、ID token
- AWS Secrets Manager 中的 Cosmos Key
- `infra/aws/terraform.tfvars`
- `infra/azure/terraform.tfvars`
- `.env`、`.env.local` 中的私有凭据
- `*.tfstate`、`*.tfstate.*`
- `.venv/`、`frontend/node_modules/`、`build/`、`.terraform/`

队友可以使用自己的 AWS IAM 身份和 Azure 登录账号访问同一个开发环境。需要发布 Lambda、ECR 镜像或 Azure Function 时，账号必须具有相应的发布权限。

## 3. 本地依赖与统一解释器规则

Windows 和 macOS 都必须先激活一个 Python `3.12` 环境，再运行项目命令。脚本只使用当前 `PATH` 中的 `python`，不会创建环境，也不会绑定 Conda 环境名或本机绝对路径。Windows 当前可使用团队已有的 Conda 环境；macOS 可使用 Conda 或自行创建的虚拟环境。

还需安装 Node.js/npm、Terraform、Docker Desktop、AWS CLI、Azure CLI 和 Azure Functions Core Tools 4。激活 Python 环境后，从项目根目录统一检查：

```text
python scripts/check-environment.py
```

检查器会打印实际 `sys.executable`、Python 版本、每个工具的路径和版本，并检查 Docker daemon。任何 `MISSING` 或 `FAIL` 都应先解决。

## 4. 初始化依赖

### 4.1 Windows PowerShell

```powershell
conda activate 5225A2
python scripts/check-environment.py
.\scripts\bootstrap.ps1
```

### 4.2 macOS

可激活已有 Conda 环境，或创建任意名称的 Python 3.12 虚拟环境：

```bash
python3.12 -m venv <environment-directory>
source <environment-directory>/bin/activate
python scripts/check-environment.py
bash scripts/bootstrap.sh
```

`bootstrap` 使用当前 Python 安装后端开发依赖和 Azure Function 依赖，并在 `frontend` 中执行 `npm ci`。

## 5. 配置前端

前端只连接 AWS API Gateway，不直接连接 Azure Function。在 `frontend/.env.local` 中写入：

```dotenv
VITE_API_BASE_URL=https://j85cs8gf3d.execute-api.ap-southeast-2.amazonaws.com
```

该文件已被 Git 忽略，不要提交。不要把 OAuth client secret 或访问令牌写入任何前端环境变量。

## 6. 登录云平台

仅运行本地 UI 时不要求云 CLI 登录；查看日志或发布时必须登录。以下命令都应在已激活的 Python 环境所在终端执行。

### 6.1 Windows PowerShell

```powershell
$env:AWS_PROFILE = "pba-team"
$env:AWS_REGION = "ap-southeast-2"
aws sso login --profile pba-team
aws sts get-caller-identity

az login
az account set --subscription 6932a700-63c2-4df8-8964-c5e0e2b906e2
az account show --output table
```

如果团队身份不是 SSO profile，先按管理员提供的方式执行 `aws configure --profile pba-team`。AWS 输出 Account 应为 `983367475562`。

### 6.2 macOS

```bash
export AWS_PROFILE=pba-team
export AWS_REGION=ap-southeast-2
aws sso login --profile pba-team
aws sts get-caller-identity

az login
az account set --subscription 6932a700-63c2-4df8-8964-c5e0e2b906e2
az account show --output table
```

## 7. 启动和端口检查

本地完整应用固定使用后端 `8000` 和前端 `5173`。Cognito 回调依赖 `http://localhost:5173`，不要让 Vite 自动切换到 `5174`。

Windows：

```powershell
Get-NetTCPConnection -LocalPort 5173,8000 -State Listen -ErrorAction SilentlyContinue
.\scripts\start-local.ps1
```

如端口被旧进程占用，先查看 PID，再明确停止目标进程：

```powershell
Get-NetTCPConnection -LocalPort 5173 -State Listen | Select-Object LocalPort,OwningProcess
Stop-Process -Id <PID>
```

macOS：

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
bash scripts/start-local.sh
```

确认 PID 后可用 `kill <PID>` 结束旧进程。启动后打开 `http://localhost:5173/login`；按 Ctrl+C 会同时结束由脚本启动的前后端进程。

## 8. 页面功能测试

### 8.1 登录和退出

1. 点击 `Create an account`。
2. 使用队友自己的邮箱和密码注册，并在项目注册页填写 `Given name` 和 `Family name`；这些值作为 Cognito 标准属性提交。
3. 在邮箱中输入 Cognito 验证码。
4. 返回登录页面并登录。
5. 如果首次登录跳转到 `/profile`，填写 `Given name` 和 `Family name`，点击 `Save and continue`。
6. 确认可以看到主工作区。
7. 点击 `Sign out`，确认返回登录页。
8. 再次登录，确认会话恢复正常且不会重复要求姓名。

外部登录按钮只应在对应 Cognito provider 已成功部署后由 `/auth/config` 返回。当前 Terraform state 尚未确认，不要为了启用按钮执行 `terraform apply`。state 恢复并由团队完成 Google provider 注册/部署后，先完成一次浏览器 consent 和登录，再运行以下只读检查：

```powershell
python scripts\check_external_provider.py `
  --user-pool-id <pool-id> --app-client-id <client-id> `
  --provider Google --region ap-southeast-2 --require-user
```

macOS 在已激活的 Python 3.12 环境中运行：

```bash
python scripts/check_external_provider.py \
  --user-pool-id <pool-id> --app-client-id <client-id> \
  --provider Google --region ap-southeast-2 --require-user
```

检查必须同时确认 provider、app client authorization-code flow、email/given_name/family_name mapping 和 `EXTERNAL_PROVIDER` 用户记录。人工证据应包含 Google consent、Cognito federated user、登录后的姓名/email claims，以及退出后再次登录；截图不得包含 token 或 client secret。

### 8.2 上传和去重

准备 `.jpg`/`.png` 图片（最大 25 MiB）或 `.mp4`/`.mov` 视频（最大 512 MiB、最长 120 秒）。前端会在计算 checksum 和创建 reservation 前拒绝超限文件。

1. 在 `Upload wildlife media` 中选择文件。
2. 点击 `Upload to archive`。
3. 在 `Your media library` 中等待状态从 `Processing` 变成 `Ready`。
4. 图片应显示缩略图；视频应显示视频预览或缩略图。
5. 再次上传完全相同的文件。
6. 页面应提示文件已经存在，不应创建新的媒体记录。

### 8.3 查询

在 `Search wildlife media` 中测试：

1. `Species`：输入一个已识别的物种名称。
2. `Tag counts`：输入物种并将 `Minimum count` 设为 `1`。
3. 添加第二个 tag，确认多个 tag 是同时满足的 AND 查询。
4. `Thumbnail URL`：在浏览器开发者工具的 Elements 或 Network 中复制缩略图请求 URL，输入后确认返回对应原图。不要把预签名 URL 发到聊天中。
5. 在 `Media management` 的 `Query file` 上传一张图片，确认返回相似媒体。

查询结果中：

- 图片应能预览缩略图，点击后打开原图。
- 视频应能打开原始视频。
- 查询文件本身不应出现在媒体库中。

### 8.4 手动标签和删除

1. 在 `Media management` 上传一个查询文件并点击 `Find matching media`。
2. 选择一条或多条结果。
3. 在 `Tags` 输入，例如 `night, field-test`。
4. 点击 `Add tags`。
5. 刷新页面，确认操作完成。
6. 选择结果并点击 `Remove tags`，确认标签可以删除。
7. 在查询页面选择 `Tag counts`，输入 `night`，最小数量填 `1`，确认可以查到带有该手动 tag 的媒体。
8. 选择一条测试媒体，点击 `Delete selected` 并确认。
9. 确认媒体库记录消失。

手动 tag 是存在型标签：`night:1` 可以匹配，`night:2` 不会匹配。

### 8.5 订阅页面

1. 输入邮箱和要关注的 tag，例如 `dingo, night`。
2. 点击 `Create subscription`。
3. 打开邮箱中的 AWS SNS confirmation 链接。
4. 刷新页面，确认状态从 `Pending confirmation` 变为 `Active`。
5. 测试编辑 tag 和删除订阅。
6. 验证完整通知链路时，创建一个唯一测试 tag（例如 `notification-test`），在 `Media management` 中选中媒体并添加相同手动 tag。
7. 确认收到主题为 `Pacific BioArchive: notification-test detected` 的邮件。

当前订阅页面已支持订阅记录的创建、读取、编辑和删除，SNS 邮箱确认和标签匹配通知链路已经实现。测试完成后移除测试标签并删除测试订阅。

## 9. 测试、构建与发布

以下流程不运行 Terraform。云资源已存在，但 Terraform backend/state 归属尚未确认，因此禁止直接执行 `terraform plan` 或 `terraform apply`；先由团队确认 backend，并把现存资源 import 到正确 state。

### 9.1 标准测试与静态验证

Windows：

```powershell
.\scripts\test-backend.ps1
.\scripts\test-contracts.ps1
.\scripts\test-frontend.ps1
.\scripts\validate-infra.ps1
```

macOS：

```bash
bash scripts/test-backend.sh
bash scripts/test-contracts.sh
bash scripts/test-frontend.sh
bash scripts/validate-infra.sh
```

`validate-infra` 会生成 Linux/Python 3.12 Lambda ZIP、运行 Terraform contract tests、执行 `fmt -check`、`init -backend=false -lockfile=readonly` 和 `validate`。它不会执行 `plan` 或 `apply`。

### 9.2 只修改前端

使用上面的 `test-frontend` 脚本完成 test/build，再用 `start-local` 启动。当前前端是本地 Vite 页面，不发布到 AWS。

### 9.3 修改 AWS API

Lambda 当前为 `x86_64`。共享构建任务始终下载 `manylinux2014_x86_64`、CPython 3.12 wheels，不能把 Windows/macOS native site-packages 直接压入 ZIP。

Windows：

```powershell
.\scripts\build-aws-api-package.ps1
aws lambda update-function-code --function-name pacific-bioarchive-development-api --zip-file fileb://build/aws-api.zip
aws lambda wait function-updated --function-name pacific-bioarchive-development-api
```

macOS：

```bash
bash scripts/build-aws-api-package.sh
aws lambda update-function-code \\
  --function-name pacific-bioarchive-development-api \\
  --zip-file fileb://build/aws-api.zip
aws lambda wait function-updated \\
  --function-name pacific-bioarchive-development-api
```

### 9.4 修改 Azure Function

每次修改 Azure Function 代码或 Python 依赖后，必须先重新生成白名单 staging 目录，再从该目录发布；不要直接从项目根目录执行 `func publish`，以免扫描本地测试文件、模型或权限受限目录。

Windows：

```powershell
.\scripts\stage-azure-function.ps1
Set-Location build\azure-function-app
func azure functionapp publish pacific-bioarchive-development-data-pba826 --python
```

macOS：

```bash
bash scripts/stage-azure-function.sh
(cd build/azure-function-app && \\
  func azure functionapp publish pacific-bioarchive-development-data-pba826 --python)
```

### 9.5 修改 Worker 或 ML 模型

Worker 需要 `mdv5a.pt`、`model.pt` 和 `labels.txt`。默认目录是项目根目录的 `models/`；也可传入其他目录。构建固定使用 `linux/amd64`，与 x86_64 Lambda 一致并兼容 Apple Silicon Mac。

Windows：

```powershell
.\scripts\build-push-aws-worker-image.ps1 `
  -RepositoryUri 983367475562.dkr.ecr.ap-southeast-2.amazonaws.com/pacific-bioarchive-development-media-worker `
  -Tag ml-v2 `
  -ModelDirectory <model-directory>
```

macOS：

```bash
bash scripts/build-push-aws-worker-image.sh \\
  983367475562.dkr.ecr.ap-southeast-2.amazonaws.com/pacific-bioarchive-development-media-worker \\
  --tag ml-v2 \\
  --model-directory <model-directory>
```

脚本自行验证 AWS account、登录 ECR、推送镜像，并输出不可变的 `repository@sha256:digest`。然后更新 Worker：

```powershell
aws lambda update-function-code --function-name pacific-bioarchive-development-media-worker --image-uri '<repository@sha256:digest>'
aws lambda wait function-updated --function-name pacific-bioarchive-development-media-worker
```

macOS 可使用同一 AWS CLI 命令并用反斜线换行。

### 9.6 更新 Terraform provider lockfile

只有 provider 版本约束改变时才运行。脚本同时记录 Windows x86_64、Intel Mac、Apple Silicon Mac 和 Linux x86_64 校验值：

```powershell
.\scripts\lock-terraform-providers.ps1
```

```bash
bash scripts/lock-terraform-providers.sh
```

## 10. 云端健康检查

检查 API 和 Azure Function：

```bash
curl -i https://j85cs8gf3d.execute-api.ap-southeast-2.amazonaws.com/health
curl -i https://pacific-bioarchive-development-data-pba826.azurewebsites.net/health
```

检查 Worker：

```bash
aws lambda invoke \\
  --function-name pacific-bioarchive-development-media-worker \\
  --cli-binary-format raw-in-base64-out \\
  --payload '{"health_check":true}' \\
  /tmp/pba-worker-health.json
jq . /tmp/pba-worker-health.json

aws lambda invoke \\
  --function-name pacific-bioarchive-development-media-worker \\
  --cli-binary-format raw-in-base64-out \\
  --payload '{"model_check":true}' \\
  /tmp/pba-worker-model.json
jq . /tmp/pba-worker-model.json
```

期望结果：

```json
{"status":"ok","database":"cosmos"}
{"status":"ok","model":"loaded"}
```

查看 Worker 日志：

```bash
aws logs tail \\
  /aws/lambda/pacific-bioarchive-development-media-worker \\
  --since 10m \\
  --format short
```

查看 API 日志：

```bash
aws logs tail \\
  /aws/lambda/pacific-bioarchive-development-api \\
  --since 10m \\
  --format short
```

## 11. 常见问题

### 登录后回到登录页

确认页面地址是 `http://localhost:5173`，不是 `5174`，并确认 `frontend/.env.local` 中的 API URL 正确。

### 页面显示 API 请求失败

先执行：

```bash
curl -i https://j85cs8gf3d.execute-api.ap-southeast-2.amazonaws.com/health
```

如果健康检查失败，检查 AWS API 状态和队友的网络连接。

### 上传后一直是 Processing

执行 Worker 的 `health_check` 和 `model_check`。如果 Worker 正常，再检查 Worker CloudWatch 日志和 SQS/DLQ。

### 缩略图显示 unavailable

等待几秒后点击 `Refresh library`。如果仍然没有缩略图，检查 Worker 日志和 S3 `derived/` 对象。

### `401 Access token is invalid`

退出后重新登录并重新执行操作。不要复制旧 token，也不要把 token 发到聊天中。

### Azure 发布返回 403

确认 Azure 账号有该 Subscription 或 Resource Group 的 Function App 发布权限，并使用允许的 Azure region。该错误不是前端代码错误。

## 12. 测试完成标准

队友完成以下项目后，可以认为本地页面和现有云端环境基本可用：

- 登录、注册、验证邮箱、退出登录成功
- 图片上传成功并生成缩略图
- 视频上传成功并完成处理
- 重复文件不会新增记录
- Species 和 Tag counts 查询返回正确结果
- 多标签查询使用 AND 逻辑
- 上传文件查询不会永久保存查询文件
- 手动标签可以批量添加、删除和查询
- 测试媒体可以删除
- 订阅记录可以创建、编辑、删除
- SNS 邮箱确认成功，匹配标签后可以收到通知邮件
- AWS API、Azure Function、Worker 健康检查通过

如果通知验证失败，先检查订阅状态是否为 `Active`，再查看 API Lambda 日志和 SNS 订阅状态。

## 13. 提交修改

修改完成后先测试，再提交：

```bash
python -m pytest -q

cd frontend
npm test -- --run
npm run build
cd ..

git status
git diff --check
git add frontend backend scripts infra TEAM_FRONTEND_RUNBOOK.md
git commit -m "Describe and verify application changes"
git push origin main
```

不要使用 `git add .` 提交未经检查的本地配置或构建文件。
