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

## 3. 本地依赖

需要安装：

- Python `3.12`
- Node.js `20` 或更高版本
- npm
- AWS CLI
- Azure CLI
- PowerShell 7 (`pwsh`)
- Azure Functions Core Tools 4 (`func`)
- Docker Desktop（只有重新构建 Worker 镜像时需要）
- `jq`（命令行检查 JSON 时需要）

检查安装情况：

```bash
python3.12 --version
node --version
npm --version
aws --version
az version
pwsh --version
func --version
docker --version
jq --version
```

## 4. 获取源码并安装依赖

如果从 GitHub 获取：

```bash
git clone https://github.com/makaakam/pacific-bioarchive-team-dev.git
cd pacific-bioarchive-team-dev
```

如果使用压缩包，先解压，然后进入项目根目录：

```bash
cd /绝对路径/pacific-bioarchive-team-dev
```

创建 Python 虚拟环境并安装开发依赖：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pip install -r requirements-azure-functions.txt
```

安装前端依赖：

```bash
cd frontend
npm ci
cd ..
```

## 5. 配置前端

前端只连接 AWS API Gateway，不直接连接 Azure Function。创建 `frontend/.env.local`：

```bash
printf '%s\n' \\
  'VITE_API_BASE_URL=https://j85cs8gf3d.execute-api.ap-southeast-2.amazonaws.com' \\
  > frontend/.env.local
```

该文件已被 Git 忽略，不要提交。

## 6. 登录云平台

队友使用自己的 AWS 身份登录同一个 AWS Account：

```bash
aws configure --profile pba-team
export AWS_PROFILE=pba-team
export AWS_REGION=ap-southeast-2
aws sts get-caller-identity
```

输出中的 Account 应为 `983367475562`。

登录 Azure：

```bash
az login
az account set --subscription 6932a700-63c2-4df8-8964-c5e0e2b906e2
az account show -o table
```

如果只是运行前端，AWS/Azure CLI 登录不是必需的；如果要查看日志或发布代码，则必需。

## 7. 启动前端

必须使用端口 `5173`，因为 Cognito 已配置以下回调地址：

```text
http://localhost:5173/auth/callback
http://localhost:5173
```

启动：

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

浏览器打开：

```text
http://localhost:5173/login
```

不要直接使用 Vite 自动分配的 `5174`。如果 `5173` 被占用：

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
kill <PID>
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## 8. 页面功能测试

### 8.1 登录和退出

1. 点击 `Create an account`。
2. 使用队友自己的邮箱和密码注册，并填写 Cognito 页面实际显示的资料字段。
3. 在邮箱中输入 Cognito 验证码。
4. 返回登录页面并登录。
5. 如果首次登录跳转到 `/profile`，填写 `Given name` 和 `Family name`，点击 `Save and continue`。
6. 确认可以看到主工作区。
7. 点击 `Sign out`，确认返回登录页。
8. 再次登录，确认会话恢复正常且不会重复要求姓名。

### 8.2 上传和去重

准备一个小于 5 GB 的 `.jpg`、`.png`、`.mp4` 或 `.mov` 文件。

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

## 9. 发布应用代码后的操作

### 9.1 只修改前端

修改 `frontend/src` 后重新运行：

```bash
cd frontend
npm test -- --run
npm run build
npm run dev -- --port 5173
```

前端代码不需要发布到 AWS，因为当前是本地 Vite 页面。

### 9.2 修改 AWS API

修改 `backend/aws_api` 或其依赖后：

```bash
cd /项目根目录
source .venv/bin/activate
./scripts/build-aws-api-package.sh

aws lambda update-function-code \\
  --function-name pacific-bioarchive-development-api \\
  --zip-file fileb://build/aws-api.zip

aws lambda wait function-updated \\
  --function-name pacific-bioarchive-development-api
```

### 9.3 修改 Azure Function

修改 `backend/azure_api`、Cosmos repository 或 Azure 查询逻辑后：

```bash
cd /项目根目录
source .venv/bin/activate
func azure functionapp publish \\
  pacific-bioarchive-development-data-pba826 \\
  --python
```

例如，手动 tag 参与 `Tag counts` 查询的逻辑就在 Azure media repository 中；修改后必须重新发布 Azure Function。

### 9.4 修改 Worker 或 ML 模型

Worker 镜像需要以下模型文件：

```text
mdv5a.pt
model.pt
labels.txt
```

登录 ECR：

```bash
aws ecr get-login-password --region ap-southeast-2 |
docker login \\
  --username AWS \\
  --password-stdin \\
  983367475562.dkr.ecr.ap-southeast-2.amazonaws.com
```

构建并推送镜像：

```bash
pwsh ./scripts/build-push-aws-worker-image.ps1 \\
  -RepositoryUri 983367475562.dkr.ecr.ap-southeast-2.amazonaws.com/pacific-bioarchive-development-media-worker \\
  -Tag ml-v2 \\
  -ModelDirectory /绝对路径/PacificBioArchive
```

脚本会输出不可变的 `repository@sha256:digest`。将该完整 URI 用于更新 Worker：

```bash
aws lambda update-function-code \\
  --function-name pacific-bioarchive-development-media-worker \\
  --image-uri '完整的repository@sha256:digest'

aws lambda wait function-updated \\
  --function-name pacific-bioarchive-development-media-worker
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
