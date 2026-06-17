"""
Serialization utility functions for RenderDoc data types.
"""

import renderdoc as rd

from .helpers import sanitize_sentinel


# ShaderVariable VarType enum integer mapping (validated against
# renderdoc.VarType.__members__ at runtime: Float=0, Double=1, Half=2,
# SInt=3, UInt=4, SShort=5, UShort=6, SLong=7, ULong=8, SByte=9, UByte=10,
# Bool=11, Enum=12, Struct=13).
_VARTYPE_NAMES = {
    0: "float", 1: "double", 2: "half",
    3: "int", 4: "uint",
    5: "short", 6: "ushort",
    7: "long", 8: "ulong",
    9: "byte", 10: "ubyte",
    11: "bool",
    12: "enum", 13: "struct",
}


def _shader_var_type_str(sv):
    """Build a friendly type string from a ShaderVariable (e.g. float4x4)."""
    try:
        sv_rows = getattr(sv, "rows", 1) or 1
        sv_cols = getattr(sv, "columns", 1) or 1

        vt = getattr(sv, "type", None)
        if vt is None:
            return "unknown"

        base = getattr(vt, "baseType", None)
        rows = getattr(vt, "rows", sv_rows) or sv_rows
        cols = getattr(vt, "columns", sv_cols) or sv_cols

        if base is not None:
            try:
                base_int = int(base)
            except Exception:
                base_int = -1
            base_name = _VARTYPE_NAMES.get(base_int, None)
            if base_name is None:
                name_attr = getattr(base, "name", None)
                base_name = (name_attr or str(base)).lower()
        else:
            try:
                base_int = int(vt)
            except Exception:
                base_int = -1
            base_name = _VARTYPE_NAMES.get(base_int, "unknown")
            rows = sv_rows
            cols = sv_cols

        if rows > 1 and cols > 1:
            return "%s%dx%d" % (base_name, rows, cols)
        if cols > 1:
            return "%s%d" % (base_name, cols)
        if rows > 1:
            return "%s%d" % (base_name, rows)
        return base_name
    except Exception:
        return "unknown"


def _read_shader_var_value(sv):
    """Extract scalar/vector/matrix value from a ShaderVariable."""
    try:
        rows = getattr(sv, "rows", 1) or 1
        cols = getattr(sv, "columns", 1) or 1
        total = max(rows * cols, 1)

        val_obj = getattr(sv, "value", None)
        if val_obj is None:
            return None

        vt = getattr(sv, "type", None)
        try:
            vt_int = int(vt)
        except Exception:
            vt_int = -1

        def _arr(attr, count, cast):
            arr = getattr(val_obj, attr, None)
            if arr is None:
                return None
            try:
                n = len(arr)
                return [cast(arr[i]) for i in range(min(count, n))]
            except Exception:
                return None

        raw = None
        if vt_int == 1:    raw = _arr("f64v", total, float)
        elif vt_int == 2:  raw = _arr("f16v", total, float)
        elif vt_int == 3:  raw = _arr("s32v", total, int)
        elif vt_int == 4:  raw = _arr("u32v", total, int)
        elif vt_int == 5:  raw = _arr("s16v", total, int)
        elif vt_int == 6:  raw = _arr("u16v", total, int)
        elif vt_int == 7:  raw = _arr("s64v", total, int)
        elif vt_int == 8:  raw = _arr("u64v", total, int)
        elif vt_int == 9:  raw = _arr("s8v", total, int)
        elif vt_int == 10: raw = _arr("u8v", total, int)
        elif vt_int == 11: raw = _arr("u32v", total, bool)
        elif vt_int in (12, 13):
            raw = _arr("u32v", total, int)
        else:
            raw = _arr("f32v", total, float)
            if raw is None:
                raw = _arr("u32v", total, int)

        if not raw:
            return None

        if rows <= 1 and cols <= 1:
            return raw[0] if raw else None
        if rows <= 1:
            return raw
        return [raw[r * cols : (r + 1) * cols] for r in range(rows)]
    except Exception:
        return None


def _shader_var_to_dict(sv, _depth=0, expand_depth=2, member_limit=-1, _parent_path=""):
    """Convert a ShaderVariable to a JSON-serializable dict (recursive)."""
    name = getattr(sv, "name", "") or ""
    if _parent_path:
        if name.startswith("["):
            current_path = "%s%s" % (_parent_path, name)
        else:
            current_path = "%s.%s" % (_parent_path, name)
    else:
        current_path = name

    members = list(getattr(sv, "members", None) or [])
    first_m_name = str(getattr(members[0], "name", "")) if members else ""
    is_array = len(members) > 0 and "[" in first_m_name

    member_names = []
    for m in members:
        m_name = str(getattr(m, "name", ""))
        if m_name.startswith("["):
            member_names.append("%s%s" % (current_path, m_name))
        elif "[" in m_name:
            member_names.append(m_name)
        else:
            member_names.append("%s.%s" % (current_path, m_name))

    var = {
        "name": name,
        "type": _shader_var_type_str(sv),
        "offset": sanitize_sentinel(getattr(sv, "byteOffset", 0)),
        "rows": getattr(sv, "rows", 1) or 1,
        "columns": getattr(sv, "columns", 1) or 1,
        "is_array": is_array,
        "array_size": len(members) if is_array else None,
        "member_names": member_names,
        "value": None,
    }

    if members:
        if _depth < expand_depth:
            if member_limit != -1 and len(members) > member_limit:
                var["truncated"] = True
                var["total_count"] = len(members)
                var["showing"] = member_limit
                to_process = members[:member_limit]
            else:
                to_process = members

            child_dicts = []
            for m in to_process:
                child_dicts.append(_shader_var_to_dict(
                    m, _depth + 1, expand_depth, member_limit, current_path
                ))
            if child_dicts:
                var["members"] = child_dicts
    else:
        var["value"] = _read_shader_var_value(sv)

    return var


class Serializers:
    """Serialization utility functions (static methods)"""

    @staticmethod
    def serialize_flags(flags):
        """Convert ActionFlags to list of strings"""
        flag_names = []
        flag_map = [
            (rd.ActionFlags.Drawcall, "Drawcall"),
            (rd.ActionFlags.Dispatch, "Dispatch"),
            (rd.ActionFlags.Clear, "Clear"),
            (rd.ActionFlags.PushMarker, "PushMarker"),
            (rd.ActionFlags.PopMarker, "PopMarker"),
            (rd.ActionFlags.SetMarker, "SetMarker"),
            (rd.ActionFlags.Present, "Present"),
            (rd.ActionFlags.Copy, "Copy"),
            (rd.ActionFlags.Resolve, "Resolve"),
            (rd.ActionFlags.GenMips, "GenMips"),
            (rd.ActionFlags.PassBoundary, "PassBoundary"),
            (rd.ActionFlags.Indexed, "Indexed"),
            (rd.ActionFlags.Instanced, "Instanced"),
            (rd.ActionFlags.Auto, "Auto"),
            (rd.ActionFlags.Indirect, "Indirect"),
            (rd.ActionFlags.ClearColor, "ClearColor"),
            (rd.ActionFlags.ClearDepthStencil, "ClearDepthStencil"),
            (rd.ActionFlags.BeginPass, "BeginPass"),
            (rd.ActionFlags.EndPass, "EndPass"),
        ]
        for flag, name in flag_map:
            if flags & flag:
                flag_names.append(name)
        return flag_names

    @staticmethod
    def serialize_variables(variables, expand_depth=2, member_limit=-1):
        """Serialize ShaderVariable list into JSON-friendly dicts.

        Recursive (nested struct/array), type-aware (all 14 VarTypes),
        matrix-aware (row-major list-of-lists), sentinel-cleaned.

        Args:
            variables: iterable of ShaderVariable
            expand_depth: how deep to recurse into nested members (default 2)
            member_limit: cap members per level (-1 = unlimited)
        """
        result = []
        for var in variables or []:
            try:
                result.append(_shader_var_to_dict(
                    var, _depth=0, expand_depth=expand_depth, member_limit=member_limit
                ))
            except Exception as e:
                result.append({"name": getattr(var, "name", "?"), "error": str(e)})
        return result

    @staticmethod
    def shader_var_to_dict(sv, expand_depth=2, member_limit=-1):
        """Single-variable wrapper around the recursive serializer."""
        return _shader_var_to_dict(sv, 0, expand_depth, member_limit, "")

    @staticmethod
    def parse_member_path(path):
        """Split a member path string into name/index segments.

        e.g. ``_child0[10]`` -> ``['_child0', '[10]']``,
             ``matrix.row0[2]`` -> ``['matrix', 'row0', '[2]']``.
        """
        import re

        segments = []
        for part in str(path or "").replace("][", "].[").split("."):
            if not part:
                continue
            segments.extend(re.findall(r"[^.\[\]]+|\[\d+\]", part))
        return segments

    @staticmethod
    def find_member_by_path(variables, path):
        """Walk a ShaderVariable tree by dotted/index path.

        Compatible with both DX naming (`[N]`) and GLES naming (`parent[N]`).
        Returns the matching ShaderVariable or None.
        """
        if not path:
            return None
        segments = Serializers.parse_member_path(path)
        if not segments:
            return None

        current = list(variables or [])
        found = None
        prev_name = ""

        for seg in segments:
            found = None
            for var in current:
                if str(getattr(var, "name", "")) == seg:
                    found = var
                    break
            # GLES fallback: '[N]' segment may need to be matched as 'parent[N]'.
            if found is None and seg.startswith("[") and prev_name:
                gles_name = "%s%s" % (prev_name, seg)
                for var in current:
                    if str(getattr(var, "name", "")) == gles_name:
                        found = var
                        break
            if found is None:
                return None
            prev_name = str(getattr(found, "name", ""))
            current = list(getattr(found, "members", None) or [])

        return found

    @staticmethod
    def serialize_actions(
        actions,
        structured_file,
        include_children,
        marker_filter=None,
        exclude_markers=None,
        event_id_min=None,
        event_id_max=None,
        only_actions=False,
        flags_filter=None,
        _in_matching_marker=False,
    ):
        """
        Serialize action list to JSON-compatible format with filtering.

        Args:
            actions: List of actions to serialize
            structured_file: Structured file for action names
            include_children: Include child actions in hierarchy
            marker_filter: Only include actions under markers containing this string
            exclude_markers: Exclude actions under markers containing these strings
            event_id_min: Only include actions with event_id >= this value
            event_id_max: Only include actions with event_id <= this value
            only_actions: Exclude marker actions (PushMarker/PopMarker/SetMarker)
            flags_filter: Only include actions with these flags
            _in_matching_marker: Internal flag for marker_filter recursion
        """
        serialized = []

        # Build flags filter set for efficient lookup
        flags_filter_set = None
        if flags_filter:
            flags_filter_set = set(flags_filter)

        for action in actions:
            name = action.GetName(structured_file)
            flags = action.flags

            # Check if this is a marker
            is_push_marker = flags & rd.ActionFlags.PushMarker
            is_set_marker = flags & rd.ActionFlags.SetMarker
            is_pop_marker = flags & rd.ActionFlags.PopMarker
            is_marker = is_push_marker or is_set_marker or is_pop_marker

            # 1. exclude_markers check - skip this marker and all its children
            if exclude_markers and is_marker:
                if any(ex in name for ex in exclude_markers):
                    continue

            # 2. marker_filter check - track if we're inside a matching marker
            in_matching = _in_matching_marker
            if marker_filter:
                if is_push_marker and marker_filter in name:
                    in_matching = True

            # 3. Determine if action passes event_id range filter
            # For markers with children, we check children even if marker is outside range
            in_range = True
            if not is_marker:
                if event_id_min is not None and action.eventId < event_id_min:
                    in_range = False
                if event_id_max is not None and action.eventId > event_id_max:
                    in_range = False

            # 4. only_actions check - skip markers but process their children
            if only_actions and is_marker:
                if include_children and action.children:
                    child_actions = Serializers.serialize_actions(
                        action.children,
                        structured_file,
                        include_children,
                        marker_filter=marker_filter,
                        exclude_markers=exclude_markers,
                        event_id_min=event_id_min,
                        event_id_max=event_id_max,
                        only_actions=only_actions,
                        flags_filter=flags_filter,
                        _in_matching_marker=in_matching,
                    )
                    serialized.extend(child_actions)
                continue

            # 5. flags_filter check - only for non-markers
            if flags_filter_set and not is_marker:
                flag_names = Serializers.serialize_flags(flags)
                if not any(f in flags_filter_set for f in flag_names):
                    continue

            # 6. Check if this action should be included based on marker_filter
            passes_marker_filter = not marker_filter or in_matching

            # 7. For markers with children, check if any children pass filters
            children_result = []
            has_passing_children = False
            if include_children and action.children:
                children_result = Serializers.serialize_actions(
                    action.children,
                    structured_file,
                    include_children,
                    marker_filter=marker_filter,
                    exclude_markers=exclude_markers,
                    event_id_min=event_id_min,
                    event_id_max=event_id_max,
                    only_actions=only_actions,
                    flags_filter=flags_filter,
                    _in_matching_marker=in_matching,
                )
                has_passing_children = len(children_result) > 0

            # Include the action if:
            # - It passes all filters (for leaf actions)
            # - It's a marker with children that pass filters (to maintain hierarchy)
            should_include = False
            if is_marker:
                # Include marker if it has children that pass filters
                should_include = has_passing_children and passes_marker_filter
            else:
                # Include leaf action if it passes all filters
                should_include = in_range and passes_marker_filter

            if should_include:
                flag_names = Serializers.serialize_flags(flags)
                item = {
                    "event_id": action.eventId,
                    "action_id": action.actionId,
                    "name": name,
                    "flags": flag_names,
                    "num_indices": action.numIndices,
                    "num_instances": action.numInstances,
                }
                if children_result:
                    item["children"] = children_result
                serialized.append(item)

        return serialized
