"""
Resource information service for RenderDoc.
"""

import base64
import struct

import renderdoc as rd

from ..utils import Parsers


class ResourceService:
    """Resource information service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _find_texture_by_id(self, controller, resource_id):
        """Find texture by resource ID"""
        target_id = Parsers.extract_numeric_id(resource_id)
        for tex in controller.GetTextures():
            tex_id_str = str(tex.resourceId)
            tex_id = Parsers.extract_numeric_id(tex_id_str)
            if tex_id == target_id:
                return tex
        return None

    def _resource_name(self, resource_id):
        try:
            name = self.ctx.GetResourceName(resource_id)
            return name or ""
        except Exception:
            return ""

    # =================================================================
    # Catalog: list textures / buffers
    # =================================================================

    def list_textures(self, name_filter=None):
        """List every texture in the capture (with optional substring filter)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"textures": []}

        def callback(controller):
            items = []
            for tex in controller.GetTextures():
                name = self._resource_name(tex.resourceId)
                if name_filter and name_filter.lower() not in (name or "").lower():
                    continue
                items.append({
                    "resource_id": str(tex.resourceId),
                    "name": name,
                    "width": tex.width,
                    "height": tex.height,
                    "depth": tex.depth,
                    "array_size": tex.arraysize,
                    "mip_levels": tex.mips,
                    "format": str(tex.format.Name()),
                    "dimension": str(tex.type),
                    "msaa_samples": tex.msSamp,
                    "byte_size": tex.byteSize,
                })
            result["textures"] = items

        self._invoke(callback)
        return result

    def list_buffers(self, name_filter=None):
        """List every buffer in the capture (with optional substring filter)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"buffers": []}

        def callback(controller):
            items = []
            for buf in controller.GetBuffers():
                name = self._resource_name(buf.resourceId)
                if name_filter and name_filter.lower() not in (name or "").lower():
                    continue
                item = {
                    "resource_id": str(buf.resourceId),
                    "name": name,
                    "length": buf.length,
                }
                # 'creationFlags' / 'usage' may not exist on all backends
                for attr in ("creationFlags", "type"):
                    if hasattr(buf, attr):
                        try:
                            item[attr] = str(getattr(buf, attr))
                        except Exception:
                            pass
                items.append(item)
            result["buffers"] = items

        self._invoke(callback)
        return result

    # =================================================================
    # Buffer contents
    # =================================================================

    def get_buffer_contents(self, resource_id, offset=0, length=0):
        """Get raw buffer data as base64."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            try:
                rid = Parsers.parse_resource_id(resource_id)
            except Exception:
                result["error"] = "Invalid resource ID: %s" % resource_id
                return

            buf_desc = None
            for buf in controller.GetBuffers():
                if buf.resourceId == rid:
                    buf_desc = buf
                    break

            if not buf_desc:
                result["error"] = "Buffer not found: %s" % resource_id
                return

            actual_length = length if length > 0 else buf_desc.length
            data = controller.GetBufferData(rid, offset, actual_length)

            result["data"] = {
                "resource_id": resource_id,
                "length": len(data),
                "total_size": buf_desc.length,
                "offset": offset,
                "content_base64": base64.b64encode(data).decode("ascii"),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    # Typed buffer reader: parses a buffer as a flat array of a single type.
    _TYPED_FORMATS = {
        "float32": ("f", 4), "float": ("f", 4),
        "float16": ("e", 2), "half": ("e", 2),
        "int32": ("i", 4), "int": ("i", 4),
        "uint32": ("I", 4), "uint": ("I", 4),
        "int16": ("h", 2), "short": ("h", 2),
        "uint16": ("H", 2), "ushort": ("H", 2),
        "int8": ("b", 1), "byte": ("b", 1),
        "uint8": ("B", 1), "ubyte": ("B", 1),
        "int64": ("q", 8),
        "uint64": ("Q", 8),
        "float64": ("d", 8), "double": ("d", 8),
    }

    def read_buffer_typed(self, resource_id, offset=0, count=64,
                           data_type="float32", components=4):
        """Parse a buffer as a flat array of N-component vectors.

        Args:
            resource_id: Buffer ResourceId.
            offset: Byte offset to start reading from.
            count: Number of vectors (groups of `components` scalars) to return.
            data_type: One of float32/float16/int32/uint32/int16/uint16/...
            components: 1..4 — vector size.

        Returns:
            ``{values: [[x,y,z,w], ...], type, components, count, offset, total_size}``
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if data_type not in self._TYPED_FORMATS:
            raise ValueError("Unsupported data_type: %s" % data_type)
        if components < 1 or components > 4:
            raise ValueError("components must be 1..4")

        fmt_char, elem_size = self._TYPED_FORMATS[data_type]
        bytes_per_vec = elem_size * components
        total_bytes = bytes_per_vec * count

        result = {"data": None, "error": None}

        def callback(controller):
            try:
                rid = Parsers.parse_resource_id(resource_id)
            except Exception:
                result["error"] = "Invalid resource ID: %s" % resource_id
                return

            buf_desc = None
            for buf in controller.GetBuffers():
                if buf.resourceId == rid:
                    buf_desc = buf
                    break
            if not buf_desc:
                result["error"] = "Buffer not found: %s" % resource_id
                return

            available = max(0, buf_desc.length - offset)
            read_bytes = min(total_bytes, available)
            data = bytes(controller.GetBufferData(rid, offset, read_bytes))

            n_vecs = len(data) // bytes_per_vec
            full_fmt = "<" + (fmt_char * components) * n_vecs
            unpacked = struct.unpack(full_fmt, data[:bytes_per_vec * n_vecs]) if n_vecs else ()

            values = []
            for i in range(n_vecs):
                vec = list(unpacked[i * components:(i + 1) * components])
                values.append(vec[0] if components == 1 else vec)

            result["data"] = {
                "resource_id": resource_id,
                "type": data_type,
                "components": components,
                "count": n_vecs,
                "offset": offset,
                "total_size": buf_desc.length,
                "values": values,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    # =================================================================
    # Texture
    # =================================================================

    def get_texture_info(self, resource_id):
        """Get texture metadata"""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"texture": None, "error": None}

        def callback(controller):
            try:
                tex_desc = self._find_texture_by_id(controller, resource_id)

                if not tex_desc:
                    result["error"] = "Texture not found: %s" % resource_id
                    return

                result["texture"] = {
                    "resource_id": resource_id,
                    "name": self._resource_name(tex_desc.resourceId),
                    "width": tex_desc.width,
                    "height": tex_desc.height,
                    "depth": tex_desc.depth,
                    "array_size": tex_desc.arraysize,
                    "mip_levels": tex_desc.mips,
                    "format": str(tex_desc.format.Name()),
                    "dimension": str(tex_desc.type),
                    "msaa_samples": tex_desc.msSamp,
                    "byte_size": tex_desc.byteSize,
                }
            except Exception as e:
                import traceback
                result["error"] = "Error: %s\n%s" % (str(e), traceback.format_exc())

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["texture"]

    def get_texture_data(self, resource_id, mip=0, slice=0, sample=0, depth_slice=None):
        """Get texture pixel data."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            tex_desc = self._find_texture_by_id(controller, resource_id)

            if not tex_desc:
                result["error"] = "Texture not found: %s" % resource_id
                return

            # Validate mip level
            if mip < 0 or mip >= tex_desc.mips:
                result["error"] = "Invalid mip level %d (texture has %d mips)" % (
                    mip,
                    tex_desc.mips,
                )
                return

            # Validate slice for array/cube textures
            max_slices = tex_desc.arraysize
            if tex_desc.cubemap:
                max_slices = tex_desc.arraysize * 6
            if slice < 0 or (max_slices > 1 and slice >= max_slices):
                result["error"] = "Invalid slice %d (texture has %d slices)" % (
                    slice,
                    max_slices,
                )
                return

            # Validate sample for MSAA
            if sample < 0 or (tex_desc.msSamp > 1 and sample >= tex_desc.msSamp):
                result["error"] = "Invalid sample %d (texture has %d samples)" % (
                    sample,
                    tex_desc.msSamp,
                )
                return

            # Calculate dimensions at this mip level
            mip_width = max(1, tex_desc.width >> mip)
            mip_height = max(1, tex_desc.height >> mip)
            mip_depth = max(1, tex_desc.depth >> mip)

            # Validate depth_slice for 3D textures
            is_3d = tex_desc.depth > 1
            if depth_slice is not None:
                if not is_3d:
                    result["error"] = "depth_slice can only be used with 3D textures"
                    return
                if depth_slice < 0 or depth_slice >= mip_depth:
                    result["error"] = "Invalid depth_slice %d (texture has %d depth at mip %d)" % (
                        depth_slice,
                        mip_depth,
                        mip,
                    )
                    return

            # Create subresource specification
            sub = rd.Subresource()
            sub.mip = mip
            sub.slice = slice
            sub.sample = sample

            # Get texture data
            try:
                data = controller.GetTextureData(tex_desc.resourceId, sub)
            except Exception as e:
                result["error"] = "Failed to get texture data: %s" % str(e)
                return

            # Extract depth slice for 3D textures if requested
            output_depth = mip_depth
            if is_3d and depth_slice is not None:
                total_size = len(data)
                bytes_per_slice = total_size // mip_depth
                slice_start = depth_slice * bytes_per_slice
                slice_end = slice_start + bytes_per_slice
                data = data[slice_start:slice_end]
                output_depth = 1

            result["data"] = {
                "resource_id": resource_id,
                "width": mip_width,
                "height": mip_height,
                "depth": output_depth,
                "mip": mip,
                "slice": slice,
                "sample": sample,
                "depth_slice": depth_slice,
                "format": str(tex_desc.format.Name()),
                "dimension": str(tex_desc.type),
                "is_3d": is_3d,
                "total_depth": mip_depth if is_3d else 1,
                "data_length": len(data),
                "content_base64": base64.b64encode(data).decode("ascii"),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
