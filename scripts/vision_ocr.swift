// Apple Vision OCR benchmark for handwritten pages (Priority 2).
// Reads PNG page images, prints recognized text lines with confidence.
// Usage: swift scripts/vision_ocr.swift <image1.png> [image2.png ...]
import Foundation
import Vision
import AppKit

func recognize(_ path: String) -> (lines: [(String, Float)], seconds: Double) {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("ERROR: cannot load \(path)")
        return ([], 0)
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["en-US"]

    let start = Date()
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    var out: [(String, Float)] = []
    do {
        try handler.perform([req])
        if let obs = req.results {
            for o in obs {
                if let c = o.topCandidates(1).first {
                    out.append((c.string, c.confidence))
                }
            }
        }
    } catch {
        print("ERROR: \(error)")
    }
    return (out, Date().timeIntervalSince(start))
}

for path in CommandLine.arguments.dropFirst() {
    let (lines, secs) = recognize(path)
    let text = lines.map { $0.0 }.joined(separator: "\n")
    print("===== \(path) | \(lines.count) lines | \(String(format: "%.2f", secs))s =====")
    print(text)
}
