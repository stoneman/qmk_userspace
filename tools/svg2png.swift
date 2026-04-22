#!/usr/bin/env swift
//
// svg2png — rasterise an SVG file to PNG using WebKit.
//
// We use WKWebView (rather than rsvg-convert or NSImage's CoreSVG path)
// because WebKit is the only SVG renderer readily available on macOS that
// renders Apple Color Emoji glyphs in colour. Both rsvg-convert and
// CoreSVG fall back to monochrome outlines for emoji glyphs in <text>.
//
// Usage:
//   svg2png <in.svg> <out.png> <width> <height> [scale]
//
// width/height are the logical (CSS px) dimensions to render at. scale
// (default 2.0) multiplies the device-pixel size of the output PNG.
//
import Cocoa
import WebKit

func die(_ msg: String, _ code: Int32 = 2) -> Never {
    FileHandle.standardError.write(Data("svg2png: \(msg)\n".utf8))
    exit(code)
}

let args = CommandLine.arguments
guard args.count >= 5 else {
    die("usage: svg2png <in.svg> <out.png> <width> <height> [scale]")
}
let inPath = args[1]
let outPath = args[2]
guard let width = Int(args[3]), let height = Int(args[4]) else {
    die("width/height must be integers")
}
let scale: CGFloat = args.count > 5 ? CGFloat(Double(args[5]) ?? 2.0) : 2.0

let inURL = URL(fileURLWithPath: inPath)
let outURL = URL(fileURLWithPath: outPath)

guard let svgData = try? Data(contentsOf: inURL),
      let svgText = String(data: svgData, encoding: .utf8) else {
    die("cannot read \(inPath)")
}

// Wrap the SVG in an HTML page that pins it to the viewport at the requested
// size. This lets us drive the rasterisation density via WKWebView's frame +
// pageZoom, decoupling the on-disk SVG dimensions from the output PNG size.
let html = """
<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  body > svg { display: block; width: \(width)px; height: \(height)px; }
</style>
</head><body>\(svgText)</body></html>
"""

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

final class Renderer: NSObject, WKNavigationDelegate {
    let webView: WKWebView
    let outURL: URL
    init(width: Int, height: Int, scale: CGFloat, outURL: URL) {
        let cfg = WKWebViewConfiguration()
        let frame = NSRect(x: 0, y: 0, width: width, height: height)
        webView = WKWebView(frame: frame, configuration: cfg)
        webView.pageZoom = scale
        // Transparent backing so the PNG isn't filled with white.
        webView.setValue(false, forKey: "drawsBackground")
        self.outURL = outURL
        super.init()
        webView.navigationDelegate = self
    }

    func load(html: String, baseURL: URL) {
        webView.loadHTMLString(html, baseURL: baseURL)
    }

    func webView(_ wv: WKWebView, didFinish nav: WKNavigation!) {
        // Give WebKit a beat to lay out and load any referenced fonts.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            let cfg = WKSnapshotConfiguration()
            cfg.afterScreenUpdates = true
            wv.takeSnapshot(with: cfg) { image, error in
                guard let image = image else {
                    die("snapshot failed: \(error?.localizedDescription ?? "?")", 3)
                }
                guard let tiff = image.tiffRepresentation,
                      let rep = NSBitmapImageRep(data: tiff),
                      let png = rep.representation(using: .png, properties: [:]) else {
                    die("PNG encode failed", 4)
                }
                do {
                    try png.write(to: self.outURL)
                } catch {
                    die("write failed: \(error)", 5)
                }
                exit(0)
            }
        }
    }

    func webView(_ wv: WKWebView, didFail nav: WKNavigation!, withError error: Error) {
        die("load failed: \(error.localizedDescription)", 6)
    }

    func webView(_ wv: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError error: Error) {
        die("provisional load failed: \(error.localizedDescription)", 7)
    }
}

let pixelW = Int((CGFloat(width) * scale).rounded())
let pixelH = Int((CGFloat(height) * scale).rounded())
let renderer = Renderer(width: pixelW, height: pixelH, scale: scale, outURL: outURL)
renderer.load(html: html, baseURL: inURL.deletingLastPathComponent())

// Bail out if WebKit never calls back.
DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
    die("timed out waiting for WebKit", 8)
}

app.run()
