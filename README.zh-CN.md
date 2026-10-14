<div align="center">

<img src="assets/icon.png" width="96" alt="ClickFlow 图标">

# ClickFlow

**在屏幕上找到图标,按你定的顺序和等待时间依次点击。**

[![最新版本](https://img.shields.io/github/v/release/Eljagi826/story-autoliker?style=flat-square)](https://github.com/Eljagi826/story-autoliker/releases/latest)
[![MIT 许可证](https://img.shields.io/badge/license-MIT-f4c430?style=flat-square)](LICENSE)
![平台](https://img.shields.io/badge/Windows_10%2F11-已测试-0078d4?style=flat-square)

[下载](#下载) · [快速开始](#快速开始) · [功能](#功能) · [详细参考](docs/reference.md) · [English](README.md)

</div>

ClickFlow 通过**图像匹配**在屏幕上找到图标并点击。你只需要排好步骤(找到这个、点击、等待、找到那个、点击、等待),ClickFlow 会不断重复,直到你让它停止。

它是通用工具,代码里没有任何针对某个网站的逻辑。自带的 `instagram_story_like` 配置(给故事点赞并跳到下一个)只是一份数据:两个步骤,一个爱心和一个"下一个"箭头。

> [!WARNING]
> 自动点赞(或任何自动化操作)可能违反 Instagram 或其他服务的使用条款,并可能导致账号被限制或封禁。请少量使用,设置较长且带随机性的延迟(抖动设置),并设置较小的最大点击次数。使用后果由你自己承担。ClickFlow 是独立项目,与 Instagram、Meta 或任何其他服务没有关联,也未获其认可。

## 下载

在[最新发布页](https://github.com/Eljagi826/story-autoliker/releases/latest)下载 **`ClickFlow.exe`**。它是适用于 Windows 10 / 11(64 位)的单个文件,免安装,不需要 Python,双击即可运行。

- 首次运行会在 `C:\Users\你的用户名\ClickFlow\` 生成配置和日志。卸载就是删除 exe 和这个文件夹。
- exe 没有代码签名,Windows SmartScreen 可能提示"未知发布者",点 **更多信息 > 仍要运行**。
- 部分杀毒软件会误报所有 PyInstaller 单文件程序。可以核对发布页里 `ClickFlow.exe.sha256` 的校验值,或者[自己从源码构建](docs/reference.md#build-the-exe-yourself)。

想用源码运行?需要 Python 3.11+。Windows 运行 `run.bat`,macOS / Linux(X11)运行 `./run.sh`,脚本会自动创建虚拟环境并启动程序。

## 快速开始

下面以 Instagram 故事配置为例。每台电脑上的图标外观都不同,所以你需要在自己的屏幕上截取一次。

1. 启动 ClickFlow,会打开 `instagram_story_like` 配置。
2. 打开故事页面,让爱心和"下一个"箭头可见。
3. 选中一个步骤,点 **Capture template...**。先拖框圈住图标,紧接着再拖一个**搜索框**,框住图标出现的区域。步骤 1 截取未点赞的(空心)爱心,步骤 2 截取"下一个"箭头。
4. 点 **Test this step**。它只查找一次,明确告诉你运行时会不会点击以及相似度。如果不会,它会说明原因并提供一键修复。
5. 点 **Dry run**,观察整个流程(只画框,不点击)。
6. 点 **Start**。开始前有 2 秒时间切换到故事窗口。

> [!IMPORTANT]
> 默认配置以最快速度运行,点击上限 500 次且无限循环。正式使用前请先调低 **Speed** 滑块和点击上限。

想安全练习,可以运行 `python -m clickflow.mock_window`,它会显示一个会统计点击次数的模拟故事页面。

## 功能

- **灵活的步骤。** 每个步骤都有自己的模板图、匹配阈值、搜索框、点击偏移、点击类型(左键、右键、双击)、等待、超时,以及找不到时怎么办(跳过、重试、停止或按备用键)。
- **速度条。** 一个滑块控制点击间隔,从无额外延迟到 1.5 秒。勾选 *Advanced* 可手动编辑每步的等待。
- **搜索框与显示器预设。** 搜索框把查找限制在图标出现的区域,无论屏幕多大,单次扫描约 55 毫秒。预设按显示器分辨率保存搜索框,并为每个显示器自动切换。
- **Test this step。** 只查找一次,告诉你运行时会不会点击。失败时诊断原因(图标大小变了、在搜索框外、阈值太严、屏幕上没有),并可一键修复。
- **安全设计。** 试运行、点击总数上限、随机延迟抖动,以及可选的结束条件图像。
- **实时日志。** 记录每一步的相似度、位置和点击坐标。

## 如何停止

以下任何一种方式都可以随时停止:

| 方式 | 操作 |
| --- | --- |
| 快捷键 | 按 **F8**(可在 *Global settings* 中修改) |
| STOP 按钮 | 点击屏幕顶部中央悬浮的红色按钮 |
| 屏幕角落 | 把鼠标移到屏幕任意一个角 |
| 程序内停止 | 点击 ClickFlow 窗口里的 *Stop* |

## 平台说明

- **Windows** 开箱即用,支持 125% / 150% 显示缩放。除非 ClickFlow 也以管理员身份运行,否则无法向管理员权限的窗口发送输入;锁屏状态下无法截屏。
- **macOS** 需要"屏幕录制"和"辅助功能"权限(停止快捷键可能还需要"输入监控")。ClickFlow 启动时会检查并提示缺少哪项。
- **Linux** 需要 X11 会话。Wayland 会阻止截屏和模拟输入。

> [!NOTE]
> ClickFlow 只在 Windows 11 上测试过,macOS 和 Linux 为尽力支持。

## 文档

- [详细参考](docs/reference.md)(英文):匹配原理、显示器预设、设计决策、架构、测试、已知限制和排错
- [参与贡献](CONTRIBUTING.md):开发环境、运行测试、设计规则
