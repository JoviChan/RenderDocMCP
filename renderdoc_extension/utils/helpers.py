"""
Common helper functions for RenderDoc operations.
"""

import renderdoc as rd


# RenderDoc C++ sentinel values for "unbound/invalid" — exposed verbatim by
# the Python bindings (~0U / ~0ULL). Surfacing them in JSON misleads LLMs.
_SENTINEL_UINT32 = 0xFFFFFFFF
_SENTINEL_UINT64 = 0xFFFFFFFFFFFFFFFF


def is_sentinel_unbound(value):
    """Detect RenderDoc sentinel values that mean 'unbound' or 'invalid'."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    return value in (_SENTINEL_UINT32, _SENTINEL_UINT64)


def sanitize_sentinel(value):
    """Return None if value is a sentinel, else pass through."""
    return None if is_sentinel_unbound(value) else value


class Helpers:
    """Common helper functions (static methods)"""

    @staticmethod
    def flatten_actions(actions):
        """Flatten hierarchical actions to a list"""
        flat = []
        for action in actions:
            flat.append(action)
            if action.children:
                flat.extend(Helpers.flatten_actions(action.children))
        return flat

    @staticmethod
    def count_children(action):
        """Count total number of children recursively"""
        count = 0
        if action.children:
            for child in action.children:
                count += 1
                count += Helpers.count_children(child)
        return count

    @staticmethod
    def get_all_shader_stages():
        """Get list of all shader stages"""
        return [
            rd.ShaderStage.Vertex,
            rd.ShaderStage.Hull,
            rd.ShaderStage.Domain,
            rd.ShaderStage.Geometry,
            rd.ShaderStage.Pixel,
            rd.ShaderStage.Compute,
        ]

    @staticmethod
    def parse_stage_string(stage_str):
        """Convert a stage string (allowing aliases) to a ShaderStage enum.

        Accepts: vertex/vs, hull/hs/tess_control/tcs, domain/ds/tess_eval/tes,
        geometry/gs, pixel/ps/fragment/fs, compute/cs.
        """
        s = (stage_str or "").lower()
        mapping = {
            "vertex": rd.ShaderStage.Vertex, "vs": rd.ShaderStage.Vertex,
            "hull": rd.ShaderStage.Hull, "hs": rd.ShaderStage.Hull,
            "tess_control": rd.ShaderStage.Hull, "tcs": rd.ShaderStage.Hull,
            "domain": rd.ShaderStage.Domain, "ds": rd.ShaderStage.Domain,
            "tess_eval": rd.ShaderStage.Domain, "tes": rd.ShaderStage.Domain,
            "geometry": rd.ShaderStage.Geometry, "gs": rd.ShaderStage.Geometry,
            "pixel": rd.ShaderStage.Pixel, "ps": rd.ShaderStage.Pixel,
            "fragment": rd.ShaderStage.Pixel, "fs": rd.ShaderStage.Pixel,
            "compute": rd.ShaderStage.Compute, "cs": rd.ShaderStage.Compute,
        }
        if s not in mapping:
            raise ValueError("Unknown shader stage: %s" % stage_str)
        return mapping[s]

    @staticmethod
    def get_pipeline_object(pipe):
        """Return the bound pipeline ResourceId, falling back to compute."""
        try:
            obj = pipe.GetGraphicsPipelineObject()
            if obj and obj != rd.ResourceId.Null():
                return obj
        except Exception:
            pass
        try:
            obj = pipe.GetComputePipelineObject()
            if obj and obj != rd.ResourceId.Null():
                return obj
        except Exception:
            pass
        return rd.ResourceId.Null()

    @staticmethod
    def is_reflection_valid(reflection):
        """A reflection object is usable only if it has a non-Null resourceId."""
        if reflection is None:
            return False
        try:
            return reflection.resourceId != rd.ResourceId.Null()
        except Exception:
            return False

    @staticmethod
    def get_resource_name(ctx, resource_id):
        """Resolve a resource ID to a human-readable name."""
        try:
            name = ctx.GetResourceName(resource_id)
            if name:
                return name
        except Exception:
            pass
        return ""
