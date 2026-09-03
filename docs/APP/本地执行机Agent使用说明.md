# 本地执行机 Agent 使用说明

## 1. 它解决什么问题

云服务器不能直接看到你本地 USB 连接的手机。Agent 模式用于把架构拆成两层：

- 云端 QAFlow：管理用例、套件、执行记录、报告和结果。
- 本地 Agent：运行在你的电脑上，连接本地手机，领取云端任务并回传执行结果。

当前第一阶段已经支持“云端派发 - 本地领取 - 状态回传”的最小闭环，默认先用 dry-run 验证链路。

## 2. 云端页面怎么看

进入：

```text
APP自动化测试 -> 执行机 Agent
```

可以看到：

- Agent 是否在线。
- 最近心跳时间。
- 同步上来的设备数量。
- 当前运行任务数量。

## 3. 本地启动命令

在本地 QAFlow 项目目录执行：

```powershell
.\venv\Scripts\python.exe scripts\qaflow_agent.py --base-url http://122.51.247.117 --username 你的账号 --password 你的密码 --once --dry-run
```

如果本地暂时没有连接手机，但只想验证链路，可以加一个模拟设备：

```powershell
.\venv\Scripts\python.exe scripts\qaflow_agent.py --base-url http://122.51.247.117 --username 你的账号 --password 你的密码 --fake-device demo-device-001 --once --dry-run
```

长期运行可以去掉 `--once`：

```powershell
.\venv\Scripts\python.exe scripts\qaflow_agent.py --base-url http://122.51.247.117 --username 你的账号 --password 你的密码 --dry-run
```

## 4. 验收步骤

1. 启动本地 Agent。
2. 在云端页面确认执行机变为在线。
3. 在设备管理里确认本地手机或模拟设备已同步。
4. 执行 APP 自动化用例时选择 `Agent` 模式。
5. Agent 领取任务后回传结果。
6. 在执行记录里确认状态从等待中变为执行中，再变为已完成。

## 5. 当前边界

第一阶段 Agent 已打通调度链路，但真机执行器还没有完全迁移到 Agent 内部。

后续需要继续补：

- Agent 内部直接执行 UI Flow。
- Agent 下载/缓存语义库和元素定位数据。
- 截图、logcat、Allure 报告完整回传。
- Agent 异常断线后的任务超时回收。

