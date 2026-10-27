# AR Preview

Blender extension for viewing your scene in augmented reality on an iPhone or iPad at 1:1 scale. Built for quick scale checks of architectural and product models in a real space.

## How it works

1. Click **View in AR** in the ARP tab of the 3D Viewport sidebar.
2. The scene is exported to USDZ and a small local web server starts on your computer.
3. Scan the QR code shown in the panel with the iPhone camera. The model opens in AR Quick Look, the AR viewer built into iOS. No app to install on the phone.
4. Change the model, click **Update AR**. The page on the phone reloads with the new version, reopen the AR view.

## Features

- One-click export and QR code, no manual file transfer
- **Merge Meshes** - exports a merged temporary copy (one draw call per material). Your scene is never modified
- **Instancing** - collection and Geometry Nodes instances exported as USD instances (when Merge is off)
- **Lock Scale** - disables pinch-to-scale in AR, the model stays 1:1
- Triangle count with a warning above a set limit
- **Save USDZ** - save the file to any folder (e.g. to send via AirDrop or Files)
- **Assign Grey Material** - one click plain grey material for selected objects (undoable)

## Requirements

- Blender 4.5 or newer
- iPhone or iPad with ARKit support (A9 chip or newer) with Safari
- Phone and computer on the same local network (Wi-Fi)
- *Allow Online Access* enabled in Preferences > System > Network
- Android is not supported (AR Quick Look is iOS only)

## Network and privacy

- The server runs only on your local network, only after you click View in AR, and stops with Stop Server or when Blender closes.
- While it runs, any device on the same network can open the address and download the exported model.
- No data is sent to the internet.
- On Windows the firewall may ask to allow Blender on private networks on the first start. Allow it, otherwise the phone cannot connect.
- The server runs on Blender's main thread (no background threads). Blender may pause for a moment while the phone downloads the model.

## Bug reports

Please report bugs at https://github.com/parametr-js/ar-preview/issues

## Development

Source code of the extension is in `ar_preview_ps/`. Build and validate the package with Blender's own tools:

```
blender --command extension build --source-dir ar_preview_ps --output-dir dist
blender --command extension validate dist/ar_preview_ps-<version>.zip
```

Functional test in a background Blender (run from the repository root):

```
blender -b --factory-startup --online-mode --python tests/test_addon.py -- result.json
```

## Third-party code

`ar_preview_ps/qrcodegen.py` - QR Code generator library by Project Nayuki, MIT License (see file header).
https://www.nayuki.io/page/qr-code-generator-library

## License

Copyright (C) 2026 Parametr Studio

Licensed under the GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
