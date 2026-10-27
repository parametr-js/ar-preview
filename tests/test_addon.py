import bpy, sys, os, json, urllib.request, traceback, re
sys.dont_write_bytecode = True  # keep the source folder clean
out = {"ver": bpy.app.version_string, "online": bpy.app.online_access}
res_file = sys.argv[sys.argv.index("--") + 1]
try:
    sys.path.insert(0, r"C:\ParametrStudio\AR_preview")
    import ar_preview_ps
    from ar_preview_ps import server, operators
    ar_preview_ps.register()
    orig = server.ThreadingHTTPServer
    server.ThreadingHTTPServer = lambda addr, h: orig(("127.0.0.1", addr[1]), h)

    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=2, location=(2, 0, 1))
    cyl = bpy.context.active_object
    for i in range(3):
        d = cyl.copy(); d.location.x += i + 1; bpy.context.collection.objects.link(d)  # linked duplicates
    s = bpy.context.scene.ar_preview
    s.port = 8770
    out["defaults"] = {"merge": s.merge_meshes, "inst": s.use_instancing, "lock": s.lock_scale}

    out["poll"] = operators.ARP_OT_view_in_ar.poll(bpy.context)
    out["view1"] = list(bpy.ops.ar_preview.view_in_ar())
    out["url"] = server.url
    base = "http://127.0.0.1:8770"
    page = urllib.request.urlopen(base + "/").read().decode()
    out["href1"] = re.search(r'href="([^"]+)"', page).group(1)
    out["rel_ar"] = 'rel="ar"' in page
    out["v1"] = urllib.request.urlopen(base + "/version").read().decode()
    m = urllib.request.urlopen(base + out["href1"].split("#")[0])
    out["model_type"] = m.headers["Content-Type"]; out["model_len"] = len(m.read())

    from pxr import Usd, UsdGeom
    st = Usd.Stage.Open(operators.temp_path())
    out["merged_meshes"] = len([p for p in st.Traverse() if p.IsA(UsdGeom.Mesh)])
    out["upAxis"] = UsdGeom.GetStageUpAxis(st)

    # second export: version bump, instancing path
    s.merge_meshes = False; s.lock_scale = False
    bpy.ops.ar_preview.view_in_ar()
    page = urllib.request.urlopen(base + "/").read().decode()
    out["href2"] = re.search(r'href="([^"]+)"', page).group(1)
    out["v2"] = urllib.request.urlopen(base + "/version").read().decode()
    st = Usd.Stage.Open(operators.temp_path())
    out["instances"] = len([p for p in st.Traverse() if p.IsInstance()])
    out["meshes2"] = len([p for p in st.Traverse() if p.IsA(UsdGeom.Mesh)])

    # Save USDZ
    s.file_path = r"D:\Temp\ar_preview_test\saved\test_out"
    out["save"] = list(bpy.ops.ar_preview.save_usdz())
    out["saved_exists"] = os.path.isfile(r"D:\Temp\ar_preview_test\saved\test_out.usdz")
    s.file_path = "//x.usdz"
    try:
        bpy.ops.ar_preview.save_usdz(); out["save_rel_unsaved"] = "no error"
    except RuntimeError as e:
        out["save_rel_unsaved"] = str(e).strip()[:120]

    # Collection instances: instancing (merge off) and merge (instances realized)
    proto = bpy.data.collections.new("Proto")
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 0))
    monkey = bpy.context.active_object
    bpy.context.collection.objects.unlink(monkey); proto.objects.link(monkey)
    for i in range(3):
        e = bpy.data.objects.new("Inst%d" % i, None)
        e.instance_type = 'COLLECTION'; e.instance_collection = proto
        e.location = (i * 3, 5, 1); bpy.context.collection.objects.link(e)
    s.merge_meshes = False; s.use_instancing = True
    s.file_path = r"D:\Temp\ar_preview_test\saved\test_inst.usdz"
    bpy.ops.ar_preview.save_usdz()
    out["tris_with_instances"] = operators.last_export["triangles"]  # 12 cube + 4x cyl + 3x 968 monkey
    st = Usd.Stage.Open(r"D:\Temp\ar_preview_test\saved\test_inst.usdz")
    out["usd_instances"] = len([p for p in st.Traverse() if p.IsInstance()])
    s.merge_meshes = True
    s.file_path = r"D:\Temp\ar_preview_test\saved\test_merge_inst.usdz"
    bpy.ops.ar_preview.save_usdz()
    st = Usd.Stage.Open(r"D:\Temp\ar_preview_test\saved\test_merge_inst.usdz")
    m = [p for p in st.Traverse() if p.IsA(UsdGeom.Mesh)]
    out["merge_inst_meshes"] = len(m)
    out["merge_inst_faces"] = len(UsdGeom.Mesh(m[0]).GetFaceVertexCountsAttr().Get())

    bpy.ops.object.select_all(action='SELECT')
    out["grey"] = list(bpy.ops.ar_preview.grey_material())
    out["temp_left"] = operators.TEMP_NAME in bpy.data.collections
    ar_preview_ps.unregister()
    out["stopped"] = not server.is_running()
except Exception:
    out["error"] = traceback.format_exc()[-1500:]
json.dump(out, open(res_file, "w"), indent=1, default=str)
