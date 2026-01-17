# RussellCsv 详细使用说明

本文档包含 RussellCsv 的功能介绍、界面说明与详细操作指引。

## 工具简介
RussellCsv 是一个基于 PyQt6 的 CSV/TSV 桌面编辑器，提供表格网格视图与源码视图切换、批量编辑、查找替换、关系图预览、安全备份等能力，适用于维护大量 CSV 数据。

## 安装与启动
### 方式一：macOS 一键启动
1. 双击 `CSV-IDE.command`
2. 首次运行会自动创建 `.venv` 并安装依赖
3. 程序启动后进入主界面

### 方式二：手动启动
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 界面结构说明
- 左侧：文件列表与筛选框
- 中间：多标签编辑区（Grid / Code 视图）
- 右侧：工具面板（Find / Cell）
- 底部：状态栏（编码、行列数、选中单元格数量）
- 顶部菜单：File / Edit / Tools / Plugin / View

## 基本工作流
### 1) 打开工程目录
- 菜单 `File > Open Folder...`
- 左侧列表会递归展示该目录下的 `.csv` / `.tsv` 文件

### 2) 打开或新建文件
- 双击左侧文件可打开
- 菜单 `File > Open File...` 可单独打开某个文件
- 菜单 `File > New` 创建新文件（默认含 `column1`）

### 3) 保存
- `File > Save` 保存当前文件
- `File > Save As...` 另存为并更新当前文件路径
- `File > Save Copy...` 另存为副本，保持当前文件路径不变
- `File > Save All` 保存所有已打开且有改动的文件

### 4) 重命名
- `File > Rename File...` 输入新文件名后重命名

### 5) 关闭与会话恢复
- 关闭标签页会提示保存未保存的改动
- 退出时会记录最后打开的文件与选中的文件
- 下次启动会自动恢复会话状态

## 编辑功能详解
### 1) Grid 视图（表格编辑）
- 直接单元格编辑
- `Delete/Backspace` 清空选中单元格
- 右键表格：
  - Insert Row Above / Below
  - Delete Row(s)
  - Insert Column Left / Right
  - Delete Column(s)
- 行头/列表头右键：
  - 插入行/列
  - 删除行/列
  - 列头双击或右键 `Rename Column` 重命名列

### 2) Code 视图（源码编辑）
- 使用 CSV 文本编辑
- 切换回 Grid 时会重新解析文本
- 如果行列数不一致，会提示 CSV Parse Error

### 3) Undo / Redo
- 菜单 `Edit > Undo / Redo`
- 支持表格编辑与插入删除的撤销重做

### 4) 单元格批量填充
- 选中同一列多个单元格，按住 `Alt` 并选中范围
- 若当前值符合 `prefix + number + suffix` 模式（如 `item_001`）
  会自动按行号递增填充

## 查找与替换
### Find 面板（右侧）
- 输入关键字点击 `Find Next`
- `Find All` 显示结果列表，双击跳转到对应单元格
- 支持大小写匹配

### Replace 对话框
- `Edit > Replace...`
- 支持替换当前匹配与替换全部
- 支持大小写匹配

## Cell 面板（右侧）
- 展示当前选中单元格坐标和内容
- 支持编辑当前值并点击 `Apply` 更新
- 支持选中多个单元格后统一赋值
- 勾选 `Increment` 且数值为整数时，可自动递增填充
- 在输入框内按 `Enter` 提交（`Shift+Enter` 换行）

## 文件列表与筛选
- 左侧输入框支持按文件名或注释过滤
- 右键文件可添加或移除备注（Comment）
- 备注内容会作为筛选关键字

## 自动保存
- 左侧 `Auto Save` 勾选后自动保存
- 切换标签、失去焦点或应用进入后台时触发保存
- 状态栏会显示 Auto Save 结果

## Safe Mode（自动备份）
入口：`Tools > Safe Mode...`

功能说明：定时将指定 CSV 文件复制到备份目录，并在界面中维护备份历史。

设置步骤：
1. 设定备份间隔（分钟）
2. 选择备份目录
3. 添加需要备份的 CSV/TSV 文件
4. 点击 `Backup Now` 可立即备份一次

备份管理：
- 日志列表显示备份时间与目标路径
- 可选择日志项执行 `Reload Selected Backup` 覆盖恢复
- 可删除选中备份文件

注意：Safe Mode 需要同时设置“间隔 + 备份目录 + 文件列表”才会自动运行。

## 关系编辑与关系图
### 关系编辑器
入口：`Tools > Edit Relations...`

作用：维护 CSV 表之间的字段关系，保存到 `relations.json`。

用法：
1. 打开某个 CSV 文件，作为 “当前表”
2. 选择当前表字段（From field）
3. 选择目标表与目标字段（To table / To field）
4. 选择关系类型（one_to_one / one_to_many）
5. 点击 `Add Relation`

Header row 设置：
- 可以输入 `head` 或数字（如 `4`）
- 表示读取表头的行号

### 关系图预览
入口：`Tools > Relationship Graph...`

功能：
- 以图形方式预览表之间关系
- 支持拖拽节点并保存布局
- 布局保存到 `relation_layout.json`

### 导入关系配置
入口：`Tools > Import Relation Config...`

说明：
- 可导入 `relations` 或布局 `nodes` 配置
- 自动写入 `relations.json` / `relation_layout.json`

## HTML 预览
工具支持 HTML 预览窗口（用于关系图与可视化文本）。
- 若内容为 HTML，会直接渲染
- 若内容类似 Mermaid 语法（graph/flowchart），会渲染为简易图形
- 支持鼠标拖拽与缩放

## 插件脚本（Plugin）
入口：`Plugin > Add Script...`

- 选择本地 Python 脚本并加入插件菜单
- 点击脚本名称可运行
- 输出结果或错误会弹窗提示
- 脚本工作目录为当前打开的根目录

## 主题
入口：`View > Light Theme / Dark Theme`

- 可切换浅色与深色主题
- 主题设置会持久保存

## 数据格式与限制
- 仅支持 `.csv` / `.tsv`
- 默认使用 UTF-8 读写
- 第一行作为表头
- 保存时根据扩展名选择分隔符（`.csv` 为 `,`，`.tsv` 为 `\t`）
- 若 CSV 行列数不一致，会提示解析错误并阻止切换到 Grid 视图

## 常见问题
### Q: 为什么切换到 Grid 时提示解析错误？
A: Code 视图中的某一行列数与表头列数不一致，需要补齐或删除多余分隔符。

### Q: 为什么 Safe Mode 不自动运行？
A: 需要设置备份间隔、备份目录并添加至少一个文件。

### Q: 关系图没有节点？
A: 需要在 Relation Editor 中先添加关系数据。
