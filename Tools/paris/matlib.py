"""Tiny material-graph builder on top of unreal.MaterialEditingLibrary (editor-side).

Materials are rebuilt in place (expressions cleared, graph re-created) so existing references from
material instances and actors survive re-runs.
"""
import unreal

import paris_common as pc

MEL = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty


def get_or_create_material(path):
    folder, name = path.rsplit("/", 1)
    pc.ensure_dir(folder)
    m = pc.EAL.load_asset(path) if pc.EAL.does_asset_exist(path) else None
    if m is None:
        m = pc.ASSET_TOOLS.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    else:
        # delete_all_material_expressions skips every other node (mutates while iterating) -> loop
        for _ in range(64):
            ex = MEL.get_material_expressions(m)
            if not ex:
                break
            for e in list(ex):
                MEL.delete_material_expression(m, e)
    return m


def get_or_create_mi(path, parent, scalars=None, vectors=None, textures=None, switches=None, two_sided=None):
    folder, name = path.rsplit("/", 1)
    pc.ensure_dir(folder)
    mi = pc.EAL.load_asset(path) if pc.EAL.does_asset_exist(path) else None
    if mi is None:
        mi = pc.ASSET_TOOLS.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    MEL.clear_all_material_instance_parameters(mi)
    for k, val in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(val))
    for k, val in (vectors or {}).items():
        c = val if isinstance(val, unreal.LinearColor) else unreal.LinearColor(*(list(val) + [1.0] * (4 - len(val))))
        MEL.set_material_instance_vector_parameter_value(mi, k, c)
    for k, val in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(mi, k, pc.load(val) if isinstance(val, str) else val)
    for k, val in (switches or {}).items():
        MEL.set_material_instance_static_switch_parameter_value(mi, k, bool(val))
    ov = mi.get_editor_property("base_property_overrides")
    ov.set_editor_property("override_two_sided", two_sided is not None)
    ov.set_editor_property("two_sided", bool(two_sided))
    mi.set_editor_property("base_property_overrides", ov)
    MEL.update_material_instance(mi)
    pc.EAL.save_asset(path, only_if_is_dirty=False)
    return mi


class Graph:
    """Build one material graph. Node helpers return expressions; use .link(src, dst, input_name)."""

    def __init__(self, path, blend=None, shading=None, domain=None, two_sided=False, **props):
        self.path = path
        self.m = get_or_create_material(path)
        if domain is not None:
            self.m.set_editor_property("material_domain", domain)
        if blend is not None:
            self.m.set_editor_property("blend_mode", blend)
        if shading is not None:
            self.m.set_editor_property("shading_model", shading)
        self.m.set_editor_property("two_sided", two_sided)
        for k, val in props.items():
            self.m.set_editor_property(k, val)
        self._x = -1800
        self._y = 0

    # ------------------------------------------------------------ primitives
    def node(self, cls, **props):
        e = MEL.create_material_expression(self.m, cls, self._x, self._y)
        self._y += 140
        if self._y > 2400:
            self._y = 0
            self._x += 300
        for k, val in props.items():
            e.set_editor_property(k, val)
        return e

    def pin(self, expr, output):
        """Reference a named output pin (e.g. texture "A", "RGBA")."""
        return (expr, output)

    def link(self, src, dst, dst_input="", src_output=""):
        if isinstance(src, tuple):
            src, src_output = src
        ok = MEL.connect_material_expressions(src, src_output, dst, dst_input)
        if not ok:
            raise RuntimeError("link failed %s.%s -> %s.%s in %s" % (src.get_name(), src_output, dst.get_name(), dst_input, self.path))
        return dst

    def out(self, prop, src, src_output=""):
        if isinstance(src, tuple):
            src, src_output = src
        if not MEL.connect_material_property(src, src_output, prop):
            raise RuntimeError("output link failed %s -> %s" % (src.get_name(), prop))

    # ------------------------------------------------------------ helpers
    def const(self, val):
        if isinstance(val, (int, float)):
            return self.node(unreal.MaterialExpressionConstant, r=float(val))
        if len(val) == 2:
            return self.node(unreal.MaterialExpressionConstant2Vector, r=val[0], g=val[1])
        if len(val) == 3:
            return self.node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(val[0], val[1], val[2], 1.0))
        return self.node(unreal.MaterialExpressionConstant4Vector, constant=unreal.LinearColor(*val))

    def scalar(self, name, default, group="Paris"):
        return self.node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=float(default), group=group)

    def vector(self, name, default, group="Paris"):
        c = unreal.LinearColor(*(list(default) + [1.0] * (4 - len(default))))
        return self.node(unreal.MaterialExpressionVectorParameter, parameter_name=name, default_value=c, group=group)

    def switch(self, name, default, a_true, b_false, group="Paris"):
        e = self.node(unreal.MaterialExpressionStaticSwitchParameter, parameter_name=name, default_value=bool(default), group=group)
        self.link(a_true, e, "True")
        self.link(b_false, e, "False")
        return e

    def tex(self, name, texture, uv=None, sampler=None, group="Paris"):
        t = pc.load(texture) if isinstance(texture, str) else texture
        e = self.node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name=name, texture=t, group=group)
        if sampler is not None:
            e.set_editor_property("sampler_type", sampler)
        if uv is not None:
            self.link(uv, e, "UVs")
        return e

    def op(self, cls, a, b=None, **props):
        e = self.node(cls, **props)
        self.link(a, e, "A")
        if b is not None:
            self.link(b, e, "B")
        return e

    def mul(self, a, b):
        return self.op(unreal.MaterialExpressionMultiply, a, b)

    def add(self, a, b):
        return self.op(unreal.MaterialExpressionAdd, a, b)

    def sub(self, a, b):
        return self.op(unreal.MaterialExpressionSubtract, a, b)

    def div(self, a, b):
        return self.op(unreal.MaterialExpressionDivide, a, b)

    def lerp(self, a, b, alpha):
        e = self.node(unreal.MaterialExpressionLinearInterpolate)
        self.link(a, e, "A")
        self.link(b, e, "B")
        self.link(alpha, e, "Alpha")
        return e

    def mask(self, src, r=False, g=False, b=False, a=False):
        e = self.node(unreal.MaterialExpressionComponentMask, r=r, g=g, b=b, a=a)
        self.link(src, e, "")
        return e

    def append(self, a, b):
        return self.op(unreal.MaterialExpressionAppendVector, a, b)

    def uv(self, index=0):
        return self.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=index)

    def world_pos(self):
        return self.node(unreal.MaterialExpressionWorldPosition)

    def world_uv(self, tile_m):
        """World XY / tile size (metres) -> float2 UV."""
        wp = self.mask(self.world_pos(), r=True, g=True)
        return self.div(wp, self.const(tile_m * 100.0))

    def per_instance_random(self):
        return self.node(unreal.MaterialExpressionPerInstanceRandom)

    def vertex_color(self):
        return self.node(unreal.MaterialExpressionVertexColor)

    def variation(self, channel="R", vc=None):
        """frac(PerInstanceRandom + VertexColor.<channel>): per-building random for merged meshes and ISMs."""
        vc = vc or self.vertex_color()
        e = self.node(unreal.MaterialExpressionFrac)
        self.link(self.add(self.per_instance_random(), self.pin(vc, channel)), e, "")
        return e

    def custom(self, code, inputs, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, desc="Custom"):
        """inputs: list of (name, expression)."""
        e = self.node(unreal.MaterialExpressionCustom)
        e.set_editor_property("code", code)
        e.set_editor_property("output_type", output_type)
        e.set_editor_property("description", desc)
        ins = []
        for n, _ in inputs:
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", n)
            ins.append(ci)
        e.set_editor_property("inputs", ins)
        for n, src in inputs:
            self.link(src, e, n)
        return e

    def flatten_normal(self, normal, flatness):
        """lerp(normal, (0,0,1), flatness)"""
        return self.lerp(normal, self.const((0.0, 0.0, 1.0)), flatness)

    def finish(self):
        MEL.layout_material_expressions(self.m)
        MEL.recompile_material(self.m)
        pc.EAL.save_asset(self.path, only_if_is_dirty=False)
        pc.log("material %s nodes=%d" % (self.path.rsplit("/", 1)[1], len(MEL.get_material_expressions(self.m))))
        return self.m
