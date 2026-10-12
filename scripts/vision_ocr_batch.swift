// Batch Apple Vision OCR for the handwritten notebook pages.
//
// For every page image it tries four orientations (0/90/180/270), scores each
// reading, and emits JSON Lines on stdout so a Python driver can persist the
// result with provenance. Nothing is written to disk here.
//
// Usage: swift scripts/vision_ocr_batch.swift <image.png> [more.png ...]
//
// Scoring is deliberately simple and is validated against the hand-built
// ground truth in data/written_pdf/benchmark/ground_truth.json before use:
//   score = 2 * plausible_word_tokens + 2 * plausible_number_tokens + line_count
// where a plausible word is >=2 letters and a plausible number starts with a
// digit. Rotated pages read as noise produce few plausible tokens.

import Foundation
import Vision
import AppKit
import ImageIO

struct Line: Codable {
    let text: String
    let confidence: Float
}

struct Candidate: Codable {
    let orientation: String
    let score: Int
    let lines: Int
}

struct PageResult: Codable {
    let path: String
    let best_orientation: String
    let best_score: Int
    let duration_s: Double
    let candidates: [Candidate]
    let lines: [Line]
    let error: String?
}

let orientations: [(String, CGImagePropertyOrientation)] = [
    ("up", .up),
    ("right", .right),
    ("down", .down),
    ("left", .left),
]

func score(_ lines: [Line]) -> Int {
    var s = lines.count
    for l in lines {
        for tok in l.text.split(whereSeparator: { $0 == " " || $0 == "\t" }) {
            let t = String(tok)
            let letters = t.filter { $0.isLetter }
            if letters.count >= 2 && t.allSatisfy({ $0.isLetter || "-'".contains($0) }) {
                s += 2
            } else if let first = t.first, first.isNumber {
                s += 2
            }
        }
    }
    return s
}

func recognize(_ cg: CGImage, _ orientation: CGImagePropertyOrientation) -> [Line] {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: cg, orientation: orientation, options: [:])
    do {
        try handler.perform([req])
    } catch {
        return []
    }
    guard let obs = req.results else { return [] }
    var out: [Line] = []
    for o in obs {
        if let c = o.topCandidates(1).first {
            out.append(Line(text: c.string, confidence: c.confidence))
        }
    }
    return out
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]

for path in CommandLine.arguments.dropFirst() {
    let started = Date()
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        let r = PageResult(
            path: path, best_orientation: "none", best_score: 0, duration_s: 0,
            candidates: [], lines: [], error: "cannot load image")
        if let d = try? encoder.encode(r), let s = String(data: d, encoding: .utf8) {
            print(s)
        }
        continue
    }

    var best: (String, Int, [Line]) = ("up", 0, [])
    var cands: [Candidate] = []
    for (name, o) in orientations {
        let lines = recognize(cg, o)
        let sc = score(lines)
        cands.append(Candidate(orientation: name, score: sc, lines: lines.count))
        if sc > best.1 {
            best = (name, sc, lines)
        }
    }

    let r = PageResult(
        path: path, best_orientation: best.0, best_score: best.1,
        duration_s: Date().timeIntervalSince(started),
        candidates: cands, lines: best.2, error: nil)
    if let d = try? encoder.encode(r), let s = String(data: d, encoding: .utf8) {
        print(s)
    }
}
