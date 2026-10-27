"""Functional test of AR Preview in a background Blender.

Run from the repository root:
    blender -b --factory-startup --online-mode --python tests/test_addon.py -- result.json

Writes a JSON report to the given path. Nothing is written into the repository:
exports go to a temporary folder. The server is bound to 127.0.0.1 (no firewall prompt).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback

import bpy

sys.dont_write_bytecode = True  # keep the source folder clean

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = sys.argv[sys.argv.index("--") + 1]
OUT_DIR = tempfile.mkdtemp(prefix="ar_preview_test_")
PORT = 8770
BASE = "http://127.0.0.1:%d" % PORT

# Client runs as a separate process: the server answers on this (main) thread only.
CLIENT = r"""
import json, sys, urllib.error, urllib.request
out = {}
for path in sys.argv[1:]:
    try:
        with urllib.request.urlopen("%s" + path, timeout=10) as r:
            body = r.read()
            out[path] = {"status": r.status, "type": r.headers["Content-Type"],
                         "cache": r.headers["Cache-Control"], "len": len(body),
                         "text": body.decode("utf-8", "replace") if len(body) < 20000 else ""}
    except urllib.error.HTTPError as e:
        out[path] = {"status": e.code}
print(json.dumps(out))
""" % BASE


def fetch(*paths):
    """Request paths from the server while pumping it. Returns (results, longest poll in s)."""
    proc = subprocess.Popen([sys.executable, "-c", CLIENT, *paths],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    longest = 0.0
    deadline = time.time() + 30
    while proc.poll() is None and time.time() < deadline:
        t = time.perf_counter()
        server.poll()
        longest = max(longest, time.perf_counter() - t)
        time.sleep(0.005)
    stdout, stderr = proc.communicate(timeout=5)
    if proc.returncode != 0:
        raise RuntimeError("client failed: " + stderr[-500:])
    return json.loads(stdout), longest


def href(page):
    return re.search(r'href="([^"]+)"', page).group(1)


out = {"blender": bpy.app.version_string, "online": bpy.app.online_access}
try:
    sys.path.insert(0, REPO)
    import ar_preview_ps
    from ar_preview_ps import operators, server
    ar_preview_ps.register()

    # Bind to loopback in the test.
    orig = server.HTTPServer
    server.HTTPServer = lambda addr, h: orig(("127.0.0.1", addr[1]), h)

    from pxr import Usd, UsdGeom

    # Scene: 1 m cube, cylinder + 3 linked duplicates
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=2, location=(2, 0, 1))
    cyl = bpy.context.active_object
    for i in range(3):
        d = cyl.copy()
        d.location.x += i + 1
        bpy.context.collection.objects.link(d)
    s = bpy.context.scene.ar_preview
    s.port = PORT
    out["defaults"] = {"merge": s.merge_meshes, "inst": s.use_instancing, "lock": s.lock_scale}

    # View in AR: page, version, model
    out["poll"] = operators.ARP_OT_view_in_ar.poll(bpy.context)
    out["view1"] = list(bpy.ops.ar_preview.view_in_ar())
    out["timer_registered"] = bpy.app.timers.is_registered(server._timer)
    r, _ = fetch("/", "/version", "/missing.txt")
    out["href1"] = href(r["/"]["text"])
    out["rel_ar"] = 'rel="ar"' in r["/"]["text"]
    out["v1"] = r["/version"]["text"]
    out["missing_status"] = r["/missing.txt"]["status"]
    r2, _ = fetch(out["href1"].split("#")[0])
    m = r2[out["href1"].split("#")[0]]
    out["model"] = {"status": m["status"], "type": m["type"], "cache": m["cache"],
                    "same_size": m["len"] == os.path.getsize(operators.temp_path())}
    st = Usd.Stage.Open(operators.temp_path())
    out["merged_meshes"] = len([p for p in st.Traverse() if p.IsA(UsdGeom.Mesh)])
    out["upAxis"] = UsdGeom.GetStageUpAxis(st)

    # Update AR: version bump, lock scale off
    s.lock_scale = False
    bpy.ops.ar_preview.view_in_ar()
    r, _ = fetch("/", "/version")
    out["href2"] = href(r["/"]["text"])
    out["v2"] = r["/version"]["text"]

    # Save USDZ (merge off, linked duplicates), unsaved .blend with // path
    s.merge_meshes = False
    s.file_path = os.path.join(OUT_DIR, "test_out")
    out["save"] = list(bpy.ops.ar_preview.save_usdz())
    out["saved_exists"] = os.path.isfile(os.path.join(OUT_DIR, "test_out.usdz"))
    s.file_path = "//x.usdz"
    try:
        bpy.ops.ar_preview.save_usdz()
        out["save_rel_unsaved"] = "no error"
    except RuntimeError as e:
        out["save_rel_unsaved"] = str(e).strip()[:120]

    # Collection instances: instancing (merge off) and merge (instances realized)
    proto = bpy.data.collections.new("Proto")
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 0))
    monkey = bpy.context.active_object
    bpy.context.collection.objects.unlink(monkey)
    proto.objects.link(monkey)
    for i in range(3):
        e = bpy.data.objects.new("Inst%d" % i, None)
        e.instance_type = 'COLLECTION'
        e.instance_collection = proto
        e.location = (i * 3, 5, 1)
        bpy.context.collection.objects.link(e)
    s.merge_meshes = False
    s.use_instancing = True
    s.file_path = os.path.join(OUT_DIR, "test_inst.usdz")
    bpy.ops.ar_preview.save_usdz()
    out["tris_with_instances"] = operators.last_export["triangles"]  # 508 + 3 x 968
    st = Usd.Stage.Open(os.path.join(OUT_DIR, "test_inst.usdz"))
    out["usd_instances"] = len([p for p in st.Traverse() if p.IsInstance()])
    s.merge_meshes = True
    s.file_path = os.path.join(OUT_DIR, "test_merge_inst.usdz")
    bpy.ops.ar_preview.save_usdz()
    st = Usd.Stage.Open(os.path.join(OUT_DIR, "test_merge_inst.usdz"))
    meshes = [p for p in st.Traverse() if p.IsA(UsdGeom.Mesh)]
    out["merge_inst_meshes"] = len(meshes)
    out["merge_inst_faces"] = len(UsdGeom.Mesh(meshes[0]).GetFaceVertexCountsAttr().Get())

    # Main-thread cost: idle poll, and a heavier model download (loopback only)
    t = time.perf_counter()
    for _ in range(100):
        server.poll()
    out["idle_poll_ms"] = round((time.perf_counter() - t) * 10, 3)  # per call
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128)  # selected, ~65k triangles
    s.selected_only = True
    bpy.ops.ar_preview.view_in_ar()
    s.selected_only = False
    r, longest = fetch("/")
    model_path = href(r["/"]["text"])
    r, longest = fetch(model_path)
    out["heavy_model"] = {"tris": operators.last_export["triangles"],
                          "mb": round(operators.last_export["size_mb"], 2),
                          "longest_poll_ms": round(longest * 1000, 1)}

    # Grey material
    bpy.ops.object.select_all(action='SELECT')
    out["grey"] = list(bpy.ops.ar_preview.grey_material())
    out["temp_left"] = operators.TEMP_NAME in bpy.data.collections

    ar_preview_ps.unregister()
    out["stopped"] = not server.is_running()
    out["timer_stopped"] = not bpy.app.timers.is_registered(server._timer)
    out["threading_in_addon"] = [
        f for f in os.listdir(os.path.join(REPO, "ar_preview_ps")) if f.endswith(".py")
        and re.search(r"^\s*(import|from)\s+(threading|queue)\b",
                      open(os.path.join(REPO, "ar_preview_ps", f), encoding="utf-8").read(), re.M)]
except Exception:
    out["error"] = traceback.format_exc()[-1500:]

with open(RESULT, "w") as f:
    json.dump(out, f, indent=1, default=str)
