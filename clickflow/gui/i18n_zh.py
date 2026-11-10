"""Chinese translations: English source text -> Chinese. Terminology follows the design hand-off copy table.

Keep every ``{placeholder}`` identical to the English source. A missing entry just shows the English text.
"""
from __future__ import annotations

import re

ZH: dict[str, str] = {
    # --- generic
    "Cancel": "取消", "OK": "确定", "Close": "关闭", "Save": "保存", "Saved": "已保存", "Unsaved": "未保存",
    "Delete": "删除", "Rename": "重命名", "New": "新建", "Create": "创建", "Clear": "清除", "Manage": "管理",
    "Default": "默认", "Stop": "停止", "Start": "开始", "Never": "从不", "Blank": "空白", "Example": "示例",
    "Error": "出错", "Set": "已设置", "Not set": "未设置", "Left": "左键", "Right": "右键", "Double": "双击",
    "Basic": "基本", "Match": "匹配", "Click": "点击", "Name": "名称", "Width": "宽", "Height": "高",
    "Display": "显示器", "Speed": "速度", "Repeat": "重复", "Clicks": "点击数", "Loops": "循环", "Elapsed": "已用时",
    "Notes": "备注", "Steps": "步骤", "Simple": "简易", "Advanced": "高级", "Enabled": "启用",
    "Slow": "慢", "Medium": "中", "Fast": "快", "Loose": "宽松", "Strict": "严格", "Infinite": "无限循环",
    "N times": "N 次", "times": "次", "clicks": "次", "No limit": "不限", "Idle": "空闲", "Running": "运行中",
    "Dry run": "试运行", "Found": "已找到", "Not found": "未找到", "Recent": "最近使用",
    "Stopped": "已停止", "Completed": "已完成", "(primary)": "（主）", "Screen {n}": "屏幕 {n}",
    "All screens": "全部屏幕",
    # --- top bar
    "Switch light / dark theme": "切换浅色 / 深色", "Switch language": "切换语言", "About / safety notes": "关于与安全提示",
    "unsaved profile": "尚未保存的档案", "My profile": "我的档案",
    # --- profile / files
    "New profile...": "新建档案…", "Open...": "打开…", "Open example profile": "打开示例档案", "Save as...": "另存为…",
    "Import .zip...": "导入 .zip…", "Export .zip...": "导出 .zip…", "Quit": "退出",
    "New profile": "新建档案", "A profile stores a set of steps and settings.": "一个档案保存一组步骤和设置。",
    "Profile name": "档案名称", "Start from": "从哪里开始", "Open profile": "打开档案", "Export profile": "导出档案",
    "Import profile": "导入档案", "New profile name": "新档案名称", "Already exists": "已存在",
    'A profile folder named "{n}" already exists.': "已经有名为「{n}」的档案文件夹。",
    "Save failed": "保存失败", "Export failed": "导出失败", "Import failed": "导入失败", "Cannot open profile": "无法打开档案",
    "Example missing": "找不到示例", "The bundled example profile could not be found.": "找不到自带的示例档案。",
    'Save changes to "{name}"?': "保存对「{name}」的更改？", "If you do not save, your changes will be lost.":
        "不保存的话，这些更改会丢失。", "Don't save": "不保存", "Profile notes": "档案备注",
    "Notes about this profile...": "写点关于这个档案的备注…",
    # --- tabs and pages
    "Step settings": "步骤设置", "Global settings": "全局设置", "Loops · hotkey · presets": "循环·热键·预设",
    "Step details": "步骤详情", "Run settings": "运行设置", "Live log": "实时日志",
    "Duplicate": "复制", "Move up": "上移", "Move down": "下移", "Add step (select a target)": "添加步骤（框选目标图）",
    # --- step editor
    "Target image": "目标图", "Re-select": "重新框选", "Test this step": "测试此步骤", "Set up": "去设置",
    "Click type": "点击方式", "Click only if found": "仅在找到时点击", "Silently skip when the target is absent": "找不到就静默跳过",
    "Use for 'already liked' checks: a missing target is not an error and no wait-after is spent.":
        "用于“已经点过赞”之类的检查：目标不存在不算错误，也不会消耗后置等待。",
    "Match strictness": "匹配严格度", "Minimum match confidence (0.50 - 1.00). Higher = stricter.": "最低匹配相似度（0.50–1.00），越高越严格。",
    "Tolerates a different on-screen size than the captured image.": "允许屏幕上的大小和截图时不同。",
    "Resize range": "缩放范围", "Auto-resize matching": "自适应大小", "Grayscale (faster)": "灰度匹配（更快）",
    "Search area": "查找范围", "Draw": "绘制", "Show boxes": "显示框", "Draw search area": "绘制查找范围",
    "Search area: whole screen": "查找范围：整个屏幕", "Search area: x={x} y={y} w={w} h={h}": "查找范围：x={x} y={y} 宽={w} 高={h}",
    "Click offset dx": "点击偏移 dx", "Waits & failure handling": "等待与失败处理", "Advanced: edit waits manually": "高级：手动编辑等待",
    "Untick = the Speed setting controls the timing of every step. Tick = each step uses its own 'Wait before / Wait after' and Speed is ignored.":
        "不勾选 = 由速度统一控制每一步的时间；勾选 = 每一步使用自己的「前置等待 / 后置等待」，速度设置不再生效。",
    "Wait before": "前置等待", "Wait after": "后置等待", "Find timeout": "查找超时",
    "How long to keep looking for the target. 0 = look exactly once.": "持续查找目标图多久。0 = 只找一次。",
    "If not found": "找不到时", "Skip and continue": "跳过并继续", "Retry N times": "重试 N 次", "Stop the run": "停止运行",
    "Press a fallback key": "按备用键", "then stop the run": "之后停止运行", "then skip the step": "之后跳过此步骤",
    "Retry": "重试", "After the last retry": "最后一次重试之后", "Fallback key": "备用键", "e.g. esc, right, ctrl+w": "例如 esc、right、ctrl+w",
    "Dims the screen; drag a rectangle around the target.": "屏幕会变暗；拖出一个框住目标图的矩形。",
    "Look for the target once and highlight it. Does NOT click.": "只找一次并框出来，不会点击。",
    "Drag a rectangle around the area where the target shows up. It is saved and applied on every run (per display preset).":
        "拖出目标图会出现的区域。它会被保存，并在每次运行时自动使用（按显示器预设分别保存）。",
    "Briefly draw the search areas of all steps on the screen.": "在屏幕上短暂画出所有步骤的查找范围。",
    "Speed is on Auto: before/after waits are set by Speed (fixed {s:g} s).": "速度为「自动」：前/后置等待由速度统一接管（固定 {s:g} s）。",
    "Search area set{where}: only this area is scanned, so it is faster.": "已设置查找范围{where}：只扫描此区域，速度更快。",
    "No search area{where}: the whole screen is scanned, which is slower and can pick look-alikes.":
        "未设置查找范围{where}：将扫描整个屏幕，速度较慢，还可能认错相似的图。",
    "missing file": "文件缺失", "No target": "无目标图", "No search area": "无查找范围", "Optional": "可选",
    "Right-click": "右键", "Double-click": "双击", "End condition": "结束条件",
    "Stop the run as soon as this image is seen.": "一看到这张图就停止运行。", "Stop as soon as this image is seen": "看到这张图就停止",
    "Press the key you want...": "按下想用的按键…", "No target image": "没有目标图", "Select a target image for this step first.": "请先为此步骤框选目标图。",
    # --- run settings
    "Slow ({s:g} s)": "慢（{s:g} s）",
    "How long from one click to the next. Right = fastest (no added delay), left = slowest ({s:g} s between clicks).":
        "两次点击之间隔多久。向右 = 最快（不额外延迟），向左 = 最慢（每次间隔 {s:g} 秒）。",
    "Click limit": "最多点击", "Stops automatically when reached": "达到次数后自动停止",
    "Runs until you stop it": "一直运行，直到你停止", "Stops automatically after {n} loop(s)": "完成 {n} 轮后自动停止",
    "Fastest: no added delay (about {d:.2f} s between clicks)": "最快：不额外延迟（每次点击间隔约 {d:.2f} 秒）",
    "At least {iv:.2f} s between clicks": "每次点击间隔至少 {iv:.2f} 秒",
    "Manual: every step uses its own waits (Advanced > Waits & failure handling)": "手动：每一步使用自己的等待时间（高级 › 等待与失败处理）",
    "{n} display(s) detected, using preset: {name}": "检测到 {n} 个显示器，当前使用「{name}」预设",
    # --- global settings
    "Stop & limits": "停止与限制", "Stop after N empty loops": "连续无匹配 N 轮后停止",
    "Stop after this many loops in a row in which nothing was found/clicked.": "连续这么多轮都没有找到/点击任何目标后停止。",
    "Stop hotkey": "停止热键", "Global stop hotkey. Click the field, then press the key you want.": "全局停止热键。点一下输入框，再按下想用的按键。",
    "Reset to F8": "恢复 F8", "Stop when mouse hits a corner": "鼠标甩到屏幕角落即停止",
    "Timing & display": "时间与显示器", "Randomize timing": "随机化间隔", "Every wait is randomised by +/- this percentage.": "每次等待都会按这个百分比随机上下浮动。",
    "Start delay": "开始前延迟", "Scan interval": "扫描间隔",
    'Which screen to scan. "All screens" combines every monitor.': "扫描哪块屏幕。“全部屏幕”会合并所有显示器。",
    "Minimize while running": "运行时最小化",
    "Display presets": "显示器预设", "Save different search areas per screen resolution.": "按分辨率保存不同的查找范围。",
    "A preset stores the search areas (and optionally target images) for one display resolution. Edits you make while a preset is selected go into that preset.":
        "预设保存某个分辨率下的查找范围（可选目标图）。选中预设时所做的修改都会写入该预设。",
    "Auto-switch by detected resolution": "按检测到的分辨率自动切换",
    "At the start of a run, ClickFlow detects the connected monitors and picks the preset whose resolution matches (and the monitor it applies to).":
        "开始运行时，ClickFlow 会检测已连接的显示器，并选用分辨率匹配的预设（以及对应的显示器）。",
    "Detect again": "重新检测", "Detected displays: {x}": "已检测到：{x}", "Detected displays: none (screen capture unavailable)": "已检测到：无（无法截屏）",
    "Default (no preset)": "默认（无预设）", "New preset": "新建预设", "Rename preset": "重命名预设", "Delete preset": "删除预设",
    "Preset name": "预设名称", "A preset keeps its own search areas for one screen resolution.": "预设为某个屏幕分辨率单独保存查找范围。",
    'Delete preset "{name}" and its search areas?': "删除预设「{name}」及其查找范围？", "No displays": "没有显示器",
    "Could not detect any display (is screen capture allowed?).": "检测不到任何显示器（是否允许了屏幕录制？）。",
    "Which display is this preset for?": "这个预设用于哪块显示器？", "Invalid hotkey": "热键无效",
    "Display preset": "显示器预设", "More settings...": "更多设置…",
    # --- capture
    "Drag a rectangle around the target. Esc / right-click cancels.": "拖出一个框住目标图的矩形。Esc / 右键取消。",
    "Drag the SEARCH AREA: where this target appears. Esc / right-click cancels.": "拖出查找范围：目标图出现的区域。Esc / 右键取消。",
    "Now drag the SEARCH AREA: where this target appears (a bit bigger than the target). Esc / right-click = skip, scan the whole screen.":
        "现在拖出查找范围：目标图出现的区域（比目标图稍大一点）。Esc / 右键 = 跳过，扫描整个屏幕。",
    "Drag a rectangle around the image that means 'finished'.": "拖出表示“已完成”的那张图。", "Drag the area where the end image shows up.": "拖出结束图会出现的区域。",
    "Screen capture failed": "截屏失败",
    # --- dock, dashboard, empty state
    "Dry run (no clicks)": "试运行（不点击）", "Looks for the targets and draws boxes, but never clicks.": "只查找并框出目标，不会点击。",
    "Add a step to get started": "添加步骤后即可开始",
    "Press {key} to stop · moving the mouse into a corner also stops": "按 {key} 停止 · 鼠标甩到屏幕角落也会停止",
    "Press {key} to stop": "按 {key} 停止", "Starting in {n} s": "{n} 秒后开始", "Switch to your target window now.": "现在请切换到目标窗口。",
    "Working through {n} step(s) in order": "正在依次执行 {n} 个步骤", "Current step": "当前步骤",
    "Click progress (limit {n})": "点击进度（上限 {n} 次）", "No click limit": "不限点击次数", "Limit {n}": "上限 {n}",
    "of {n}": "共 {n} 轮", "Average {s:.1f} s per click": "平均每次点击 {s:.1f} s", "Latest match": "最近一次匹配",
    "No match yet": "还没有匹配", "Strictness {v:.2f}": "严格度 {v:.2f}",
    "Target thumbnails are hidden while running so the matcher cannot find them on screen.": "运行时目标图缩略图已隐藏，避免被屏幕上的它误匹配。",
    "Let it click for you": "让它替你自动点击",
    "Select a small image on screen (the target). ClickFlow keeps looking for it and clicks it.": "框选屏幕上要点的小图（目标图），ClickFlow 会反复查找，找到就自动点击。",
    "Select a target": "框选目标图", "Drag a box around the button or icon you want clicked.": "在屏幕上拖出要点击的按钮或图标。",
    "Pick speed and repeats": "选择速度与次数", "Three speeds; click N times or loop forever.": "三档速度，可点 N 次或无限循环。",
    "Press Start": "点击开始", "Stop any time with the hotkey. No risk of clicking too long.": "随时按热键停止，不怕点过头。",
    "Open the example profile": "打开示例档案",
    "Stopped (corner)": "已停止（鼠标到了角落）", "Click limit reached": "已达到点击上限",
    "End image seen": "看到了结束图", "A step failed": "有步骤失败", "Stopped: nothing found": "已停止：连续没有找到",
    "Invalid profile": "档案无效", "Cannot start": "无法开始",
    # --- dialogs
    "Cannot start yet": "还不能开始", "{n} thing(s) need your attention first:": "有 {n} 个问题需要先处理：",
    "Permission needed": "需要权限", "Target not found": "没找到这张目标图", 'Step "{name}": this step would NOT click.': "步骤「{name}」：运行时不会点击。",
    "Apply suggested fix": "应用建议修复", 'A fix is available. Apply it, then press "Test this step" again.': "有可用的修复。应用后请再点一次「测试此步骤」。",
    "Image-matching auto clicker": "图像识别自动点击器", "About": "关于", "Open-source licenses": "开源许可证",
    "Press the stop hotkey (default F8) at any time.": "随时按停止热键（默认 F8）。",
    "Click the red STOP button at the top of the screen.": "点击屏幕顶部的红色「STOP」浮标。", "Move the mouse into any screen corner.": "把鼠标甩到屏幕任意一个角落。",
    "Automating clicks may violate a website's or app's terms of service and can get an account limited or banned. Use low volume, sensible delays and a click limit, at your own risk.":
        "自动点击可能违反目标网站或应用的服务条款，并可能导致账号受限或被封禁。请低频使用、保留合理延迟并设置点击上限，风险自负。",
    "ClickFlow is free software under the MIT License, provided as is, without warranty. It is independent and not affiliated with any service it can be pointed at.":
        "ClickFlow 是 MIT 许可的自由软件，按“原样”提供，不含任何担保。它是独立项目，与它可能操作的任何服务无关联。",
    # --- outline icons and not-found fallbacks
    "Outline / transparent icon": "镂空 / 透明图标",
    "Ignore the background showing through the icon (e.g. an outline heart)": "忽略从图标中透出来的背景（例如空心的爱心）",
    "Compares only the icon's own lines. Use it for see-through icons drawn over photos or videos, which otherwise fail on busy backgrounds.":
        "只比对图标本身的线条。适合画在照片或视频上面的镂空图标，否则背景一花就会认不出来。",
    "Look again where it was last found": "在上次找到的位置再找一次",
    "If not found: search right there once more, a little less strictly": "找不到时：就在那个位置再找一次，稍微放宽一点严格度",
    "If still not found, click where it was last found": "仍然找不到时，直接点上次找到的位置",
    "At most {n} times in a row, and only shortly after a real match": "最多连续 {n} 次，而且只在刚刚真正找到过之后",
    "Capture": "截取", "Strictness": "严格度", "Skip if this image is there": "看到这张图就跳过",
    "Drag a rectangle around the image that means 'already done', e.g. the red (liked) heart.":
        "拖出表示“已经做过了”的那张图，例如红色（已点赞）的爱心。",
    "How closely the screen must match the 'skip if present' image.": "屏幕要和“看到就跳过”的图有多像才算看到。",
    "Checked before any fallback click: when this image is near the last position, the step is skipped. For likes, capture the red (already liked) heart.":
        "在任何兜底点击之前都会先检查：如果在上次的位置附近看到这张图，就跳过这一步。点赞场景请截取红色（已点赞）的爱心。",
    "Without a 'skip if present' image, a blind click can undo something already done (e.g. unlike a liked story).":
        "没有设置“看到就跳过”的图时，盲点可能会撤销已经做过的操作（例如把已点赞的快拍取消点赞）。",
    "Drag a rectangle around the image that means 'already done' (e.g. the red, liked heart). Esc / right-click cancels.":
        "拖出表示“已经做过了”的那张图（例如红色的已点赞爱心）。Esc / 右键取消。",
    "Outline": "镂空", "Fallback click": "兜底点击",
}


# --- run log lines produced by the (English) core, translated for display only -----------------------------

_STEP = {"left": "左键", "right": "右键", "double": "双击"}


def format_event(ev) -> str:
    m = ev.message
    mm = re.fullmatch(r"--- loop (\d+)/(\w+) ---", m)
    if mm:
        return f"第 {mm.group(1)} 轮开始" + ("" if mm.group(2) == "inf" else f" / 共 {mm.group(2)} 轮")
    mm = re.fullmatch(r"Step '(.*)'", m)
    if mm:
        return f"步骤「{mm.group(1)}」"
    mm = re.match(r"(?:\[(\w+)\] )?'(.*)': (FOUND|not found), confidence ([\d.]+) \(threshold ([\d.]+)\)", m)
    if mm:
        _tag, name, verdict, conf, thr = mm.groups()
        return (f"匹配「{name}」置信度 {float(conf):.2f}" if verdict == "FOUND"
                else f"「{name}」未找到：{float(conf):.2f}（严格度 {thr}）")
    mm = re.fullmatch(r"(\[dry-run\] would )?(left|right|double)-click at \((\d+),(\d+)\)", m)
    if mm:
        dry, kind, x, y = mm.groups()
        return f"{'（试运行）将' if dry else ''}{_STEP[kind]}点击 ({x}, {y})"
    mm = re.match(r"(Run|Dry run) started: (\d+) step\(s\), loops=(\w+), click limit=(\w+)", m)
    if mm:
        _k, n, loops, limit = mm.groups()
        return f"开始 · 共 {n} 个步骤，{'无限循环' if loops == 'infinite' else loops + ' 轮'}" + ("" if limit == "none" else f"，点击上限 {limit}")
    mm = re.fullmatch(r"Step '(.*)': rescued near its last position \(confidence ([\d.]+), relaxed threshold ([\d.]+)\)", m)
    if mm:
        return f"步骤「{mm.group(1)}」：在上次的位置附近找到了（置信度 {mm.group(2)}，放宽后的严格度 {mm.group(3)}）"
    mm = re.fullmatch(r"Step '(.*)': not found, but the 'skip if present' image is there - already done, skipped", m)
    if mm:
        return f"步骤「{mm.group(1)}」：没找到目标，但看到了“看到就跳过”的图 —— 已经做过，跳过"
    mm = re.fullmatch(r"Step '(.*)': not found - blind click at its last position \((\d+)/(\d+) in a row\)", m)
    if mm:
        return f"步骤「{mm.group(1)}」：没找到 —— 直接点上次的位置（连续第 {mm.group(2)}/{mm.group(3)} 次）"
    mm = re.fullmatch(r"Step '(.*)': no blind click - (.*)", m)
    if mm:
        return f"步骤「{mm.group(1)}」：不做盲点 —— {mm.group(2)}"
    return m
