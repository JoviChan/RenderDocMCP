# RenderDoc MCP Server

让 AI 助手（Claude / Cursor / Cline / CodeMaker 等）可以直接读取 RenderDoc 抓帧数据，
进行图形调试和性能分析。**核心能力是抓取每个 draw call 的细节信息——包括 constant buffer / uniform buffer 的具名变量值**。

## 核心特性

- 🎯 **完整 cbuffer / uniform buffer 值解析** — 覆盖 D3D11/D3D12/Vulkan/OpenGL/OpenGL ES（移动端）
- 🔍 **支持递归展开** struct / array / 矩阵嵌套；按路径精确钻取
- 📊 一次拉取某个 draw 在某个 stage 的所有绑定（SRV / UAV / Sampler / CBuffer + 值）
- 📦 资源目录（textures / buffers）+ 类型化 buffer 读取（无需 base64 解码）
- ⚡ **傻瓜式安装** — `uvx --from git+https://github.com/halby24/RenderDocMCP.git`，扩展端首次启动自动安装/升级

## 一键安装

在 MCP 客户端配置里加上：

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/halby24/RenderDocMCP.git", "renderdoc-mcp"]
    }
  }
}
```

首次启动时会自动把 RenderDoc 扩展安装到 `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`（或 Linux/macOS 对应目录）。
之后在 RenderDoc 里 **Tools → Manage Extensions** 勾选 `RenderDoc MCP Bridge` 并重启 RenderDoc 即可。

后续版本升级时（`uvx` 重装包），扩展端会通过版本号比对自动覆盖更新，**不再需要手动重装**。

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

RenderDoc 内置的 Python 没有 socket 模块，所以走文件 IPC。

## MCP 工具一览

### 帧/管线分析
| 工具 | 说明 |
|------|------|
| `get_capture_status` | 当前是否加载了 capture |
| `get_frame_summary` | 整帧总览（API、统计、顶层 marker、资源数量） |
| `detect_engine` | 启发式识别引擎（Unity / Unreal / NeoX） |
| `get_draw_calls` | 拉取 draw call 树（支持 marker_filter / event_id 区间过滤） |
| `get_draw_call_details` | 单个 draw 的详细信息 |
| `get_action_timings` | GPU 计时（每个 event 的耗时） |
| `get_dispatches` | 列出所有 Compute Dispatch |
| `get_pass_drawcalls` | 同一 render pass 内的所有 draw |
| `get_pipeline_state` | 完整 pipeline state（默认带 cbuffer 值） |

### Shader / Constant Buffer ⭐ 新增
| 工具 | 说明 |
|------|------|
| `get_shader_info` | 单个 stage 的 shader 反汇编 + cbuffer 值 + 资源绑定 |
| `get_shader_resources` | 单 stage 的全部绑定（SRV+UAV+Sampler+CBuffer 值） |
| **`get_cbuffer_values`** | **专用：单个 draw 的 cbuffer/uniform 实际值（具名变量）** |
| **`expand_cbuffer_member`** | **按路径钻取深层成员（数组/嵌套 struct）** |

### 反向查找
| 工具 | 说明 |
|------|------|
| `find_draws_by_shader` | 按 shader 名找 draw |
| `find_draws_by_texture` | 按贴图名找 draw |
| `find_draws_by_resource` | 按 ResourceId 找 draw |

### 资源
| 工具 | 说明 |
|------|------|
| `list_textures` | 列出所有贴图（支持名字过滤） |
| `list_buffers` | 列出所有 buffer |
| `get_texture_info` | 贴图元信息 |
| `get_texture_data` | 贴图像素（Base64） |
| `get_buffer_contents` | buffer 原始数据（Base64） |
| **`read_buffer_typed`** | **按类型读 buffer（float32/uint16/...）直接返回数值** |

### Capture 管理
| 工具 | 说明 |
|------|------|
| `list_captures` | 列出目录下的 .rdc 文件 |
| `open_capture` | 打开指定 capture |

## 使用示例

### 抓 cbuffer 具名变量值（修复 #1 — 美术常用）
```
get_cbuffer_values(event_id=7538, stage="pixel")
# → 返回每个 cbuffer 的 slot/name/byte_size/bound_resource，
#    以及 variables: [{name: "VolumeWeight", type: "float", value: 0.0}, ...]
```

### 钻取嵌套数组 / struct
```
expand_cbuffer_member(event_id=7538, cbuffer_slot=3,
                      member_path="VolumetricFogParamsArray[5].density")
```

### 一次拉单 stage 全部绑定
```
get_shader_resources(event_id=7538, stage="pixel")
```

### 类型化 buffer 读取
```
read_buffer_typed(resource_id="ResourceId::123",
                  data_type="float32", components=3, count=1024)
# → values: [[x,y,z], [x,y,z], ...]  无需自己 base64 解码
```

## 要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（用于 `uvx` 启动）
- RenderDoc 1.20+
- 已验证：Windows + D3D11 / D3D12 / Vulkan / OpenGL ES（移动端）

## License

MIT
