"""
RenderDoc MCP Server
FastMCP 2.0 server providing access to RenderDoc capture data.
"""

from typing import Literal

from fastmcp import FastMCP

from .bridge.client import RenderDocBridge, RenderDocBridgeError
from .config import settings

# Initialize FastMCP server
mcp = FastMCP(
    name="RenderDoc MCP Server",
)

# RenderDoc bridge client
bridge = RenderDocBridge(host=settings.renderdoc_host, port=settings.renderdoc_port)


@mcp.tool
def get_capture_status() -> dict:
    """
    Check if a capture is currently loaded in RenderDoc.
    Returns the capture status and API type if loaded.
    """
    return bridge.call("get_capture_status")


@mcp.tool
def get_draw_calls(
    include_children: bool = True,
    marker_filter: str | None = None,
    exclude_markers: list[str] | None = None,
    event_id_min: int | None = None,
    event_id_max: int | None = None,
    only_actions: bool = False,
    flags_filter: list[str] | None = None,
) -> dict:
    """
    Get the list of all draw calls and actions in the current capture.

    Args:
        include_children: Include child actions in the hierarchy (default: True)
        marker_filter: Only include actions under markers containing this string (partial match)
        exclude_markers: Exclude actions under markers containing these strings (list of partial matches)
        event_id_min: Only include actions with event_id >= this value
        event_id_max: Only include actions with event_id <= this value
        only_actions: If True, exclude marker actions (PushMarker/PopMarker/SetMarker)
        flags_filter: Only include actions with these flags (list of flag names, e.g. ["Drawcall", "Dispatch"])

    Returns a hierarchical tree of actions including markers, draw calls,
    dispatches, and other GPU events.
    """
    params: dict[str, object] = {"include_children": include_children}
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    if exclude_markers is not None:
        params["exclude_markers"] = exclude_markers
    if event_id_min is not None:
        params["event_id_min"] = event_id_min
    if event_id_max is not None:
        params["event_id_max"] = event_id_max
    if only_actions:
        params["only_actions"] = only_actions
    if flags_filter is not None:
        params["flags_filter"] = flags_filter
    return bridge.call("get_draw_calls", params)


@mcp.tool
def get_frame_summary() -> dict:
    """
    Get a summary of the current capture frame.

    Returns statistics about the frame including:
    - API type (D3D11, D3D12, Vulkan, etc.)
    - Total action count
    - Statistics: draw calls, dispatches, clears, copies, presents, markers
    - Top-level markers with event IDs and child counts
    - Resource counts: textures, buffers
    """
    return bridge.call("get_frame_summary")


@mcp.tool
def find_draws_by_shader(
    shader_name: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] | None = None,
) -> dict:
    """
    Find all draw calls using a shader with the given name (partial match).

    Args:
        shader_name: Partial name to search for in shader names or entry points
        stage: Optional shader stage to search (if not specified, searches all stages)

    Returns a list of matching draw calls with event IDs and match reasons.
    """
    params: dict[str, object] = {"shader_name": shader_name}
    if stage is not None:
        params["stage"] = stage
    return bridge.call("find_draws_by_shader", params)


@mcp.tool
def find_draws_by_texture(texture_name: str) -> dict:
    """
    Find all draw calls using a texture with the given name (partial match).

    Args:
        texture_name: Partial name to search for in texture resource names

    Returns a list of matching draw calls with event IDs and match reasons.
    Searches SRVs, UAVs, and render targets.
    """
    return bridge.call("find_draws_by_texture", {"texture_name": texture_name})


@mcp.tool
def find_draws_by_resource(resource_id: str) -> dict:
    """
    Find all draw calls using a specific resource ID (exact match).

    Args:
        resource_id: Resource ID to search for (e.g. "ResourceId::12345" or "12345")

    Returns a list of matching draw calls with event IDs and match reasons.
    Searches shaders, SRVs, UAVs, render targets, and depth targets.
    """
    return bridge.call("find_draws_by_resource", {"resource_id": resource_id})


@mcp.tool
def get_draw_call_details(event_id: int) -> dict:
    """
    Get detailed information about a specific draw call.

    Args:
        event_id: The event ID of the draw call to inspect

    Includes vertex/index counts, resource outputs, and other metadata.
    """
    return bridge.call("get_draw_call_details", {"event_id": event_id})


@mcp.tool
def get_action_timings(
    event_ids: list[int] | None = None,
    marker_filter: str | None = None,
    exclude_markers: list[str] | None = None,
) -> dict:
    """
    Get GPU timing information for actions (draw calls, dispatches, etc.).

    Args:
        event_ids: Optional list of specific event IDs to get timings for.
                   If not specified, returns timings for all actions.
        marker_filter: Only include actions under markers containing this string (partial match).
        exclude_markers: Exclude actions under markers containing these strings.

    Returns timing data including:
    - available: Whether GPU timing counters are supported
    - unit: Time unit (typically "seconds")
    - timings: List of {event_id, name, duration_seconds, duration_ms}
    - total_duration_ms: Sum of all durations
    - count: Number of timing entries

    Note: GPU timing counters may not be available on all hardware/drivers.
    """
    params: dict[str, object] = {}
    if event_ids is not None:
        params["event_ids"] = event_ids
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    if exclude_markers is not None:
        params["exclude_markers"] = exclude_markers
    return bridge.call("get_action_timings", params)


@mcp.tool
def get_shader_info(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
) -> dict:
    """
    Get shader information for a specific stage at a given event.

    Args:
        event_id: The event ID to inspect the shader at
        stage: The shader stage (vertex, hull, domain, geometry, pixel, compute)

    Returns shader disassembly, constant buffer values, and resource bindings.
    """
    return bridge.call("get_shader_info", {"event_id": event_id, "stage": stage})


@mcp.tool
def get_buffer_contents(
    resource_id: str,
    offset: int = 0,
    length: int = 0,
) -> dict:
    """
    Read the contents of a buffer resource.

    Args:
        resource_id: The resource ID of the buffer to read
        offset: Byte offset to start reading from (default: 0)
        length: Number of bytes to read, 0 for entire buffer (default: 0)

    Returns buffer data as base64-encoded bytes along with metadata.
    """
    return bridge.call(
        "get_buffer_contents",
        {"resource_id": resource_id, "offset": offset, "length": length},
    )


@mcp.tool
def get_texture_info(resource_id: str) -> dict:
    """
    Get metadata about a texture resource.

    Args:
        resource_id: The resource ID of the texture

    Includes dimensions, format, mip levels, and other properties.
    """
    return bridge.call("get_texture_info", {"resource_id": resource_id})


@mcp.tool
def get_texture_data(
    resource_id: str,
    mip: int = 0,
    slice: int = 0,
    sample: int = 0,
    depth_slice: int | None = None,
) -> dict:
    """
    Read the pixel data of a texture resource.

    Args:
        resource_id: The resource ID of the texture to read
        mip: Mip level to retrieve (default: 0)
        slice: Array slice or cube face index (default: 0)
               For cube maps: 0=X+, 1=X-, 2=Y+, 3=Y-, 4=Z+, 5=Z-
        sample: MSAA sample index (default: 0)
        depth_slice: For 3D textures only, extract a specific depth slice (default: None = full volume)
                     When specified, returns only the 2D slice at that depth index

    Returns texture pixel data as base64-encoded bytes along with metadata
    including dimensions at the requested mip level and format information.
    """
    params = {"resource_id": resource_id, "mip": mip, "slice": slice, "sample": sample}
    if depth_slice is not None:
        params["depth_slice"] = depth_slice
    return bridge.call("get_texture_data", params)


@mcp.tool
def get_pipeline_state(event_id: int, include_cbuffer_values: bool = True) -> dict:
    """
    Get the full graphics pipeline state at a specific event.

    Args:
        event_id: The event ID to get pipeline state at
        include_cbuffer_values: When True (default), every stage's constant
            buffers carry resolved variable values (names + numeric values).
            Set False to get a lighter dump with declarations only.

    Returns detailed pipeline state including:
    - Bound shaders with entry points for each stage
    - Shader resources (SRVs): textures and buffers with dimensions, format, slot, name
    - UAVs (RWTextures/RWBuffers): resource details with dimensions and format
    - Samplers: addressing modes, filter settings, LOD parameters
    - Constant buffers: slot, size, variable names + values
    - Render targets and depth target
    - Viewports and input assembly state
    """
    return bridge.call(
        "get_pipeline_state",
        {"event_id": event_id, "include_cbuffer_values": include_cbuffer_values},
    )


@mcp.tool
def get_cbuffer_values(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] = "pixel",
    cbuffer_slot: int | None = None,
    expand_depth: int = 2,
    member_offset: int = 0,
    member_limit: int = -1,
) -> dict:
    """
    Read constant-buffer / uniform-buffer values for a specific draw call.

    Resolves the bound buffer + range and decodes named variables (e.g.
    `VolumeWeight`, `LocalFogPackedParams`, `FrameTime`...) with their
    actual numeric values. Works on D3D11/D3D12, Vulkan, OpenGL and
    OpenGL ES (mobile).

    Args:
        event_id: Draw call event ID.
        stage: Shader stage. Default 'pixel'.
        cbuffer_slot: Bind slot filter (b0/b3/...). None = all CBs.
        expand_depth: How deep to recurse into nested struct/array members
            (0 = top-level only, 2 = default).
        member_offset: Pagination offset for top-level variables.
        member_limit: Cap members per level, -1 = unlimited.

    Returns:
        success/api/shader_id plus a list of constant_buffers, each with
        slot/name/byte_size/bound_resource and a recursive variables list.
    """
    params: dict[str, object] = {
        "event_id": event_id,
        "stage": stage,
        "expand_depth": expand_depth,
        "member_offset": member_offset,
        "member_limit": member_limit,
    }
    if cbuffer_slot is not None:
        params["cbuffer_slot"] = cbuffer_slot
    return bridge.call("get_cbuffer_values", params)


@mcp.tool
def expand_cbuffer_member(
    event_id: int,
    cbuffer_slot: int,
    member_path: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] = "pixel",
    expand_depth: int = 2,
    member_limit: int = -1,
) -> dict:
    """
    Drill into a deeply-nested cbuffer/uniform-buffer member by path.

    Use after `get_cbuffer_values` when a struct/array was truncated.
    Path examples: `_child0[10]`, `matrix.row0[2]`, `LocalFogPackedParams.x`.
    """
    return bridge.call(
        "expand_cbuffer_member",
        {
            "event_id": event_id,
            "cbuffer_slot": cbuffer_slot,
            "member_path": member_path,
            "stage": stage,
            "expand_depth": expand_depth,
            "member_limit": member_limit,
        },
    )


@mcp.tool
def get_shader_resources(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
) -> dict:
    """
    One-shot dump of every binding for a given shader stage.

    Returns SRVs, UAVs, samplers, AND constant buffers (with resolved values)
    in a single call — equivalent to RenderDoc's Pipeline State viewer for
    that stage.
    """
    return bridge.call(
        "get_shader_resources",
        {"event_id": event_id, "stage": stage},
    )


@mcp.tool
def list_textures(name_filter: str | None = None) -> dict:
    """
    List every texture resource in the capture (with optional name substring filter).

    Returns metadata: width/height/depth, mip levels, array size, format,
    dimension type, MSAA samples, byte size.
    """
    params: dict[str, object] = {}
    if name_filter is not None:
        params["name_filter"] = name_filter
    return bridge.call("list_textures", params)


@mcp.tool
def list_buffers(name_filter: str | None = None) -> dict:
    """
    List every buffer resource in the capture (with optional name substring filter).
    """
    params: dict[str, object] = {}
    if name_filter is not None:
        params["name_filter"] = name_filter
    return bridge.call("list_buffers", params)


@mcp.tool
def read_buffer_typed(
    resource_id: str,
    offset: int = 0,
    count: int = 64,
    data_type: Literal[
        "float32", "float16", "int32", "uint32", "int16", "uint16",
        "int8", "uint8", "int64", "uint64", "float64",
    ] = "float32",
    components: int = 4,
) -> dict:
    """
    Read a buffer as a typed flat array of N-component vectors.

    Use this instead of `get_buffer_contents` (raw base64) when you know
    the layout — e.g. position buffers, instance data, structured buffers.
    """
    return bridge.call(
        "read_buffer_typed",
        {
            "resource_id": resource_id,
            "offset": offset,
            "count": count,
            "data_type": data_type,
            "components": components,
        },
    )


@mcp.tool
def get_dispatches(
    event_id_min: int | None = None,
    event_id_max: int | None = None,
    marker_filter: str | None = None,
) -> dict:
    """
    List every Compute Dispatch in the capture (optionally filtered by event
    id range or marker substring).
    """
    params: dict[str, object] = {}
    if event_id_min is not None:
        params["event_id_min"] = event_id_min
    if event_id_max is not None:
        params["event_id_max"] = event_id_max
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    return bridge.call("get_dispatches", params)


@mcp.tool
def get_pass_drawcalls(event_id: int) -> dict:
    """
    Get every draw within the same render pass as ``event_id``.

    Useful when you want to see the full set of draws that share render
    targets / pass setup with a given draw call.
    """
    return bridge.call("get_pass_drawcalls", {"event_id": event_id})


@mcp.tool
def detect_engine() -> dict:
    """
    Heuristic engine detection (Unity / Unreal / NeoX) from marker patterns.
    """
    return bridge.call("detect_engine", {})


@mcp.tool
def list_captures(directory: str) -> dict:
    """
    List all RenderDoc capture files (.rdc) in the specified directory.

    Args:
        directory: The directory path to search for capture files

    Returns a list of capture files with their metadata including:
    - filename: The capture file name
    - path: Full path to the file
    - size_bytes: File size in bytes
    - modified_time: Last modified timestamp (ISO format)
    """
    return bridge.call("list_captures", {"directory": directory})


@mcp.tool
def open_capture(capture_path: str) -> dict:
    """
    Open a RenderDoc capture file (.rdc).

    Args:
        capture_path: Full path to the capture file to open

    Returns success status and information about the opened capture.
    Note: This will close any currently open capture.
    """
    return bridge.call("open_capture", {"capture_path": capture_path})


def _extension_dir():
    """Resolve qrenderdoc's user-extensions dir for the current OS."""
    import os
    import sys
    from pathlib import Path
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        return Path(appdata) / "qrenderdoc" / "extensions"
    return Path.home() / ".local" / "share" / "qrenderdoc" / "extensions"


_BUNDLED_EXTENSION_VERSION = "1.1.0"


def _read_installed_extension_version(dest):
    """Read version from an installed extension.json. Returns '' on failure."""
    try:
        import json
        with open(dest / "extension.json", encoding="utf-8") as f:
            return str(json.load(f).get("version", ""))
    except Exception:
        return ""


def _version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".") if x.isdigit())
    except Exception:
        return ()


def _ensure_extension_installed():
    """Install or upgrade the in-process qrenderdoc extension.

    Two sources are tried in order:
    1. Source files bundled inside this wheel (`mcp_server/_extension_payload`).
       Preferred — works offline, version-locked to the MCP server.
    2. Public GitHub zip (fallback) — for source installs that don't have
       the payload bundled.

    Re-installs whenever the installed extension's version is older than
    `_BUNDLED_EXTENSION_VERSION`, so existing users get our updates after
    `uvx --from git+...` rebuilds the package.
    """
    import shutil
    import sys
    from pathlib import Path

    ext_dir = _extension_dir()
    if ext_dir is None:
        return
    dest = ext_dir / "renderdoc_mcp_bridge"

    installed_version = _read_installed_extension_version(dest) if dest.exists() else ""
    if installed_version and _version_tuple(installed_version) >= _version_tuple(_BUNDLED_EXTENSION_VERSION):
        return  # Already up to date.

    # 1) Try the bundled payload (preferred).
    try:
        payload = Path(__file__).parent / "_extension_payload"
        if payload.exists() and (payload / "extension.json").exists():
            ext_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(payload, dest)
            print(
                "[RenderDoc MCP] Installed extension v%s to %s\n"
                "[RenderDoc MCP] Restart RenderDoc for changes to take effect."
                % (_BUNDLED_EXTENSION_VERSION, dest),
                file=sys.stderr,
            )
            return
    except Exception as e:
        print(
            "[RenderDoc MCP] Bundled-payload install failed: %s; falling back to GitHub..." % e,
            file=sys.stderr,
        )

    # 2) Fallback: download from GitHub.
    import tempfile
    import zipfile
    from io import BytesIO
    from urllib.error import URLError
    from urllib.request import urlopen

    GITHUB_ZIP_URL = "https://github.com/halby24/RenderDocMCP/archive/refs/heads/main.zip"
    EXTENSION_SUBDIR = "RenderDocMCP-main/renderdoc_extension"

    print("[RenderDoc MCP] Downloading extension from GitHub...", file=sys.stderr)
    try:
        resp = urlopen(GITHUB_ZIP_URL, timeout=30)
        zip_data = BytesIO(resp.read())

        with zipfile.ZipFile(zip_data) as zf:
            ext_files = [
                f for f in zf.namelist()
                if f.startswith(EXTENSION_SUBDIR + "/") and not f.endswith("/")
            ]
            if not ext_files:
                print("[RenderDoc MCP] Extension files not found in GitHub repo", file=sys.stderr)
                return

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_ext = Path(tmpdir) / "renderdoc_mcp_bridge"
                tmp_ext.mkdir()

                for filepath in ext_files:
                    rel = filepath[len(EXTENSION_SUBDIR) + 1:]
                    if not rel:
                        continue
                    target = tmp_ext / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(filepath) as src, open(target, "wb") as dst:
                        dst.write(src.read())

                ext_dir.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(tmp_ext, dest)

        print(
            "[RenderDoc MCP] Extension installed to %s\n"
            "[RenderDoc MCP] Enable in RenderDoc: Tools > Manage Extensions > "
            "RenderDoc MCP Bridge. Restart RenderDoc for updates to apply." % dest,
            file=sys.stderr,
        )
    except (URLError, OSError, Exception) as e:
        print(
            "[RenderDoc MCP] Auto-install failed: %s\n"
            "[RenderDoc MCP] Manually run: python scripts/install_extension.py" % e,
            file=sys.stderr,
        )


def main():
    """Run the MCP server"""
    _ensure_extension_installed()
    mcp.run()


if __name__ == "__main__":
    main()
