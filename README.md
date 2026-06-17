# RenderDoc MCP Server

让 AI 助手（Claude / Cursor / Cline / CodeMaker 等）可以直接读取 RenderDoc 抓帧数据，
进行图形调试和性能分析。**51 个工具，完整覆盖 RenderDoc Pipeline State Viewer 全部能力**。

## 核心特性

- 🎯 **完整 cbuffer / uniform buffer 值解析** — D3D11/D3D12/Vulkan/OpenGL/OpenGL ES（移动端）全覆盖
- 🔍 **递归展开** struct / array / 矩阵嵌套；按路径精确钻取
- 📊 一次拉取某个 draw 在某个 stage 的所有绑定（SRV / UAV / Sampler / CBuffer + 值）
- 📦 资源目录 + 分布统计 + 按名/格式/数值搜索
- 🎨 贴图 / Buffer 导出到磁盘（PNG/JPG/HDR/EXR/DDS）
- 🐛 Shader 调试（像素级单步）、Shader 编辑（热替换）
- 🔬 Pixel History — 看哪些 draw 写了某个像素
- 📈 RDG 渲染依赖图（Mermaid / DOT）
- 🕵️ 启发式问题检测（高 overdraw / 无 PS / 全屏四边形）
- 🧮 `execute_python` — 在 RenderDoc 上下文执行任意代码（power-user escape hatch）
- ⚡ **傻瓜式安装 + 自动升级** — 扩展端首次启动自动安装，版本更新自动覆盖

## 一键安装

在 MCP 客户端配置里加上：

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "uvx",
      "args": [
        "--refresh-package", "renderdoc-mcp",
        "--from", "git+https://github.com/JoviChan/RenderDocMCP.git",
        "renderdoc-mcp"
      ]
    }
  }
}
```

首次启动自动把 RenderDoc 扩展安装到 `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`。
在 RenderDoc 里 **Tools → Manage Extensions** 勾选 `RenderDoc MCP Bridge` 并重启一次即可。

后续版本升级时 `--refresh-package` 会自动拉最新代码，扩展端通过版本号比对自动覆盖更新。

## 架构

```
AI 客户端 (stdio)
       │
       ▼
MCP 服务进程 (Python + FastMCP)
       │ File-based IPC (%TEMP%/renderdoc_mcp/)
       ▼
RenderDoc 进程 (Bridge Extension，运行在 qrenderdoc 内置 Python 中)
```

## 全部 51 个工具

### 帧分析 & 导航
| 工具 | 说明 |
|------|------|
| `get_capture_status` | 当前是否加载了 capture |
| `get_frame_summary` | 整帧总览（API、统计、顶层 marker、资源数量） |
| `analyze_rdc` | 综合分析（action 统计 + marker 树 + 资源计数）—— 调查起点 |
| `detect_engine` | 启发式识别引擎（Unity / Unreal / NeoX） |
| `get_frame_hierarchy` | 纯 marker 树（轻量导航，可控层级深度） |
| `get_draw_calls` | draw call 层级树（支持 marker_filter / event_id 过滤） |
| `get_draw_call_details` | 单个 draw 的详细信息 |
| `get_drawcall_summary` | 简洁 draw 列表（带 shader/RT/三角形数） |
| `get_drawcall_stats` | 整帧聚合统计（按 shader / RT / 三角形数 分桶） |
| `get_action_timings` | GPU 计时（每个 event 耗时） |
| `search_actions` | 灵活 action 搜索（名字 / marker / event_id / flags） |

### Render Pass & Compute
| 工具 | 说明 |
|------|------|
| `get_all_passes` | 列出整帧所有 render pass |
| `get_pass_drawcalls` | 同一 render pass 内的所有 draw |
| `get_dispatches` | 列出所有 Compute Dispatch |
| `get_buffer_operations` | Copy / Resolve / GenMips / Clear 事件列表 |

### Pipeline State & Constant Buffer ⭐
| 工具 | 说明 |
|------|------|
| `get_pipeline_state` | 完整 pipeline state（默认含 cbuffer 值） |
| `get_shader_info` | 单 stage shader 反汇编 + cbuffer 值 + 资源绑定 |
| `get_shader_resources` | 单 stage 全部绑定一次拉（SRV+UAV+Sampler+CBuffer 值） |
| **`get_cbuffer_values`** | **cbuffer / uniform 具名变量实际值** |
| **`expand_cbuffer_member`** | **按路径钻取深层成员（数组 / struct / 矩阵）** |

### Shader 反汇编 & 反编译
| 工具 | 说明 |
|------|------|
| `list_disassembly_targets` | 可用反汇编 target（DXBC/SPIR-V/HLSL/GLSL…） |
| `disassemble_shader` | 指定 target 反汇编 |
| `decompile_shader` | HLSL / GLSL 反编译 |

### Shader 调试 🐛
| 工具 | 说明 |
|------|------|
| `debug_pixel_shader` | 在屏幕坐标 (x,y) 启动 pixel shader 调试会话 |
| `step_shader_debugger` | 单步执行，返回变量变化 |
| `get_shader_state` | 获取 debug 会话当前变量快照 |
| `free_shader_debugger` | 释放 debug 会话 |

### Shader 编辑 (实验性)
| 工具 | 说明 |
|------|------|
| `apply_shader_edit` | 编译自定义源码 → 热替换 draw 的 shader |
| `remove_shader_edit` | 撤销 shader 替换 |

### Pixel History 🔬
| 工具 | 说明 |
|------|------|
| `get_pixel_history` | 单像素完整修改历史（哪些 draw 写了它，前后值 + 深度/模板结果） |

### 反向查找
| 工具 | 说明 |
|------|------|
| `find_draws_by_shader` | 按 shader 名找 draw |
| `find_draws_by_texture` | 按贴图名找 draw |
| `find_draws_by_resource` | 按 ResourceId 找 draw |

### 资源管理
| 工具 | 说明 |
|------|------|
| `list_textures` | 列出所有贴图（支持名字过滤） |
| `list_buffers` | 列出所有 buffer |
| `get_texture_info` | 贴图元信息 |
| `get_texture_data` | 贴图像素（Base64） |
| `get_buffer_contents` | buffer 原始数据（Base64） |
| `read_buffer_typed` | 类型化 buffer 读取（float32/uint16/...）直接返回数值 |
| `get_resource_overview` | 资源高层概览（总数 + 总字节） |
| `get_texture_stats` | 贴图分布统计（按格式/尺寸分桶 + Top N） |
| `get_buffer_stats` | Buffer 分布统计（按大小分桶 + Top N） |
| `search_texture` | 按名/格式/尺寸搜贴图 |
| `search_buffer` | buffer 内数值搜索（找常量/参数是否正确写入） |

### 导出
| 工具 | 说明 |
|------|------|
| `export_texture` | 保存贴图到磁盘（PNG/JPG/BMP/TGA/HDR/EXR/DDS） |
| `export_buffer` | 保存 buffer 到二进制文件 |

### RDG & 问题检测
| 工具 | 说明 |
|------|------|
| `generate_rdg_flowchart` | 生成 Mermaid / DOT 渲染依赖图 |
| `find_overlay_issues` | 启发式问题检测（高 overdraw / 无 PS / 全屏四边形） |

### Capture 管理
| 工具 | 说明 |
|------|------|
| `list_captures` | 列出目录下的 .rdc 文件 |
| `open_capture` | 打开指定 capture |

### Escape Hatch
| 工具 | 说明 |
|------|------|
| `execute_python` | 在 RenderDoc 上下文执行任意 Python 代码 |

## 使用示例

### 整帧分析（调查第一步）
```
analyze_rdc()
# → api, total actions, draw/dispatch/clear/copy counts, top markers, resource counts
```

### 抓 cbuffer 具名变量值（美术常用）
```
get_cbuffer_values(event_id=7538, stage="pixel")
# → variables: [{name: "VolumeWeight", type: "float", value: 0.0}, ...]
```

### 钻取嵌套数组 / struct
```
expand_cbuffer_member(event_id=7538, cbuffer_slot=3,
                      member_path="VolumetricFogParamsArray[5].density")
```

### Pixel History — 像素被谁写了？
```
get_pixel_history(resource_id="ResourceId::456", x=960, y=540)
# → 哪些 draw 写了这个像素，前后值，深度/模板测试结果
```

### 渲染依赖图
```
generate_rdg_flowchart(format="mermaid")
# → Mermaid 图文本，可粘贴到 Markdown 预览
```

### Shader 反编译
```
decompile_shader(event_id=7538, stage="pixel", language="hlsl")
```

## 要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（用于 `uvx` 启动）
- RenderDoc 1.20+
- 已验证：Windows + D3D11 / D3D12 / Vulkan / OpenGL ES（移动端）

## License

MIT
