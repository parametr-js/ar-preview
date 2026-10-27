# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""QR code as a Blender preview icon, drawn in the panel with template_icon.

QR matrix comes from qrcodegen.py (Project Nayuki, MIT License),
bundled with the add-on - no internet, no external dependency.
"""

import bpy.utils.previews

from .qrcodegen import QrCode

MODULE_PX = 8    # pixels per QR module
BORDER = 4       # quiet zone in modules (QR standard asks for 4)

_previews = None
_text = None     # text of the currently generated QR


def qr_pixels(text):
    """Return (size_px, flat RGBA float list) of a black-on-white QR code."""
    qr = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    modules = qr.get_size() + 2 * BORDER
    size = modules * MODULE_PX

    pixels = []
    # Blender images start at the bottom-left corner, QR rows at the top.
    for y in range(size - 1, -1, -1):
        my = y // MODULE_PX - BORDER
        for x in range(size):
            mx = x // MODULE_PX - BORDER
            v = 0.0 if qr.get_module(mx, my) else 1.0  # get_module is False outside
            pixels.extend((v, v, v, 1.0))
    return size, pixels


def icon_id(text):
    """icon_id of the QR preview for text, regenerated only when text changes."""
    global _text
    preview = _previews.get("qr") or _previews.new("qr")
    if text != _text:
        size, pixels = qr_pixels(text)
        preview.image_size = (size, size)
        preview.image_pixels_float = pixels
        preview.icon_size = (size, size)
        preview.icon_pixels_float = pixels
        _text = text
    return preview.icon_id


def register():
    global _previews
    _previews = bpy.utils.previews.new()


def unregister():
    global _previews, _text
    bpy.utils.previews.remove(_previews)
    _previews = None
    _text = None
