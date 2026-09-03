# QAFlow 智能测试平台

QAFlow 是一个面向测试团队的全栈测试平台，核心目标是把测试资产、自动化执行、测试报告、AI 辅助分析和业务测试数据工具沉淀到同一个工作台中，降低用例维护成本，提升回归测试和问题定位效率。

项目采用 Django REST Framework + Vue 3 架构，覆盖测试用例管理、接口测试、Web UI 自动化、Android APP 自动化、AI 探索测试、数据工厂和通知集成等能力。

## 项目亮点

- 自动化用例资产治理：支持用例目录、标签、优先级、生命周期、维护人、数据影响范围等治理字段，方便持续维护自动化资产。
- Android APP 自动化：从单纯录制转向“语义元素库 + 页面地图 + 用例编排 + 套件执行”的可维护方案，支持元素框选入库、复验、截图证据、logcat 导出和标准化报告。
- AI 探索测试：支持基于页面地图和受控巡检的探索任务，沉淀页面证据、风险复核、AI 分析报告和问题归档能力，为后续大模型介入执行预留接口。
- 数据工厂：提供常用测试数据生成、账号池管理、业务压测任务编排能力，支持房间列表、进退房、社区活跃、IM 消息、发布组队等可扩展业务场景。
- 报告与证据链：自动化执行结果支持标准报告、Allure 报告、步骤截图、失败证据包、logcat 日志等信息，便于测试复盘和提交缺陷。
- 通知体系：内置统一通知配置模型，支持邮件和 Webhook 机器人扩展，适合对接企微、飞书、钉钉等团队通知渠道。

## 技术栈

后端：

- Python 3.12
- Django 4.2 + Django REST Framework
- MySQL 8.0+
- Redis + Celery
- Allure / pytest
- Airtest / ADB
- Selenium / Playwright

前端：

- Vue 3 + Composition API
- Vite
- Element Plus
- Pinia
- Vue Router
- ECharts
- Monaco Editor

AI 与自动化：

- OpenAI-compatible LLM provider
- DeepSeek / Qwen / SiliconFlow 等模型配置
- browser-use
- APP 语义元素库与受控探索执行器

## 功能模块

| 模块 | 说明 |
| --- | --- |
| 测试资产中心 | 用例、套件、执行记录、报告、质量待办统一管理 |
| 需求分析 | 上传需求文档，结合 AI 生成测试点和测试用例 |
| API 测试 | 接口集合、环境变量、断言、执行历史、Allure 报告 |
| Web UI 自动化 | 页面元素、脚本、套件、执行记录和报告 |
| APP 自动化 | Android 设备管理、语义元素、页面地图、用例编排、套件执行 |
| AI 探索测试 | 受控巡检、页面证据、风险识别、AI 分析和复核归档 |
| 数据工厂 | 通用测试数据工具、账号池、业务压测任务 |
| 通知与交付 | 邮件/Webhook 通知配置，报告和证据出口 |

## 项目结构

```text
testhub_platform/
├── apps/
│   ├── app_automation/        # Android APP 自动化、AI 探索、语义库、页面地图
│   ├── api_testing/           # API 测试
│   ├── core/                  # 通用配置、统一通知等基础能力
│   ├── data_factory/          # 数据工厂、账号池、业务压测
│   ├── requirement_analysis/  # AI 需求分析和用例生成
│   ├── testcases/             # 手工测试用例
│   ├── testsuites/            # 测试套件
│   ├── executions/            # 测试执行
│   ├── reports/               # 测试报告
│   └── users/                 # 用户和认证
├── backend/                   # Django 项目配置
├── frontend/                  # Vue 前端工程
├── docs/                      # 项目文档
├── media/                     # 运行时文件目录，仅保留 .gitkeep
├── scripts/                   # 本地开发启动脚本
├── allure/                    # 内置 Allure 命令行
├── requirements.txt
└── manage.py
```

## 本地启动

### 1. 准备环境

建议版本：

- Python 3.12
- Node.js 18+
- MySQL 8.0+
- Redis 6+
- Java 17+，用于 Allure 报告
- Android SDK / ADB，用于 APP 自动化

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，按本地环境修改数据库、Redis、AI 模型和业务压测配置。

```powershell
Copy-Item .env.example .env
```

最少需要关注：

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=*
DB_HOST=localhost
DB_NAME=testhub
DB_USER=root
DB_PASSWORD=your-database-password
DB_PORT=3306
REDIS_URL=redis://127.0.0.1:6379/0
```

数据工厂和 APP 自动化涉及真实业务环境，默认不在代码里写死地址、账号和验证码。需要使用时在 `.env` 中单独配置：

```env
DATA_FACTORY_DEFAULT_BASE_URL=https://your-business-domain.example.com
DATA_FACTORY_DEFAULT_SMS_CODE=your-sms-code
DATA_FACTORY_DEFAULT_PROBE_PHONE=your-probe-phone
DATA_FACTORY_IM_RUNNER_PATH=/opt/qaflow/tools/im-runner

APP_AUTOMATION_TEST_LOGIN_PHONE=your-test-phone
APP_AUTOMATION_TEST_LOGIN_PASSWORD=your-test-password
APP_AUTOMATION_TEST_COMMUNITY_KEYWORD=your-community-keyword
APP_AUTOMATION_TEST_COMMUNITY_NAME=your-community-name
APP_AUTOMATION_TARGET_PACKAGE=com.example.demo
APP_AUTOMATION_MAIN_ACTIVITY=com.example.demo.activity.MainActivity
APP_AUTOMATION_SEARCH_ROOM_ACTIVITY=com.example.demo.activity.SearchRoomActivity
APP_AUTOMATION_PUBLISH_TEAM_ACTIVITY=com.example.demo.activity.PublishTeamActivity
APP_AUTOMATION_ROOM_ACTIVITY=com.example.demo.activity.RoomActivity
```

### 3. 安装依赖

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt

cd frontend
npm install
cd ..
```

### 4. 初始化数据库

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
```

### 5. 启动开发服务

推荐使用脚本一键启动 Redis、后端、Celery 和前端：

```powershell
.\scripts\start-dev.ps1
```

默认访问地址：

```text
Frontend: http://127.0.0.1:3000
Backend : http://127.0.0.1:8001
API Docs: http://127.0.0.1:8001/api/docs/
Admin   : http://127.0.0.1:8001/admin/
```

查看服务状态：

```powershell
.\scripts\status-dev.ps1
```

停止服务：

```powershell
.\scripts\stop-dev.ps1
```

## 手动启动

后端：

```powershell
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Celery：

```powershell
.\venv\Scripts\celery.exe -A backend worker -l info -P solo --concurrency=1
```

前端：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

## 常用命令

```powershell
# 后端检查
.\venv\Scripts\python.exe manage.py check

# 生成迁移
.\venv\Scripts\python.exe manage.py makemigrations

# 应用迁移
.\venv\Scripts\python.exe manage.py migrate

# 前端构建
cd frontend
npm run build

# APP 自动化 8 月 P0 种子用例初始化
.\venv\Scripts\python.exe manage.py bootstrap_august_p0_cases --project-id 2 --package-id 1
```

## 部署说明

生产部署建议：

- 后端使用 Gunicorn、Uvicorn 或 Daphne 托管 Django ASGI 服务。
- 前端执行 `npm run build` 后由 Nginx 托管静态资源。
- MySQL、Redis、媒体文件目录和日志目录与应用服务分离。
- `.env` 只保存在服务器，不提交到 Git。
- APP 自动化依赖 Android 设备、ADB、Airtest、Allure 和 Java，建议和普通 Web/API 能力分开评估部署资源。

Linux 部署参考：

```text
docs/APP/PROD_DEPLOY_LINUX.md
```

## 安全与开源注意事项

- 不提交 `.env`、数据库 dump、日志、截图、运行报告、真实账号、验证码、Webhook 地址。
- 数据工厂默认不绑定公司测试环境或正式环境，所有业务服务地址都通过 `.env` 或页面表单显式配置。
- APP 自动化种子用例需要目标环境测试账号和社区数据，缺少配置时管理命令会直接报错，避免生成不可用用例。
- 历史评测材料和内部分析文档建议只保留在本地，公开仓库中放脱敏后的正式说明文档。

## 验证记录

当前提交前建议至少执行：

```powershell
.\venv\Scripts\python.exe manage.py check
cd frontend
npm run build
```

已知前端构建可能出现 Vite chunk size、`web-tree-sitter` eval 等警告；如果构建成功，这些警告不阻断本地演示。

## 后续路线

短期：

- 完成企微机器人执行结果通知，推送套件/用例摘要、报告入口和日志证据入口。
- 整理部署脚本和服务器部署文档，确保新机器能按 README 跑起来。
- 准备一套脱敏演示数据和演示账号策略。

中期：

- 完善 APP 自动化语义库和 30 条以上稳定可执行用例。
- 提升套件执行速度、整体报告可读性和失败定位效率。
- 数据工厂压测场景继续插件化，避免单一大表单承载所有场景。

长期：

- AI 探索测试从“辅助分析”升级到“受控决策 + 人工复核 + 可回放用例沉淀”。
- 引入更完整的质量看板，沉淀用例覆盖率、失败趋势、缺陷定位和版本质量评估能力。
