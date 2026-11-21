import AppKit

/// A scripted walk through the editor that saves pictures of the window, for checking the UI without a person
/// (after Manimble's ShotsTest): `FIGNIMBLE_SHOTS=/some/folder Fignimble.app/Contents/MacOS/Fignimble <project>`.
/// It edits the project it is given, so give it a copy.
extension MainController {
    func runShotsIfAsked() {
        guard let dir = ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS"] else { return }
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        Task { @MainActor in
            for _ in 0..<300 where figure == nil { try? await Task.sleep(nanoseconds: 100_000_000) }
            try? await Task.sleep(nanoseconds: 800_000_000)
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "layout" { await layoutShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "features" { await featureShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "code" { await codeShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "colors" { await colorShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "parts" { await partShots(dir); return }
            shot(dir, "01-figure")
            canvas.selection = ["1"]
            await settle(); shot(dir, "02-panel-selected")
            edit(["op": "move", "oids": ["1"], "dx": 6, "dy": 4])
            await settle(); shot(dir, "03-moved")
            undoEdit(nil)
            await settle()
            canvas.selection = ["L0"]
            await settle(); shot(dir, "04-label-selected")
            edit(["op": "move", "oids": ["L0"], "dx": -2.5, "dy": -1, "labels": "all"])
            await settle(); shot(dir, "05-labels-moved")
            undoEdit(nil)
            await settle()
            // a real drag with the mouse: panel c 8 mm to the right (snapping and the move edit)
            if let c = figure?.element("2") {
                let start = CGPoint(x: c.box.midX, y: c.box.midY)
                mouse(.leftMouseDown, start)
                for i in 1...8 { mouse(.leftMouseDragged, CGPoint(x: start.x + CGFloat(i), y: start.y)) }
                shot(dir, "06a-dragging")
                mouse(.leftMouseUp, CGPoint(x: start.x + 8, y: start.y))
                await settle(); shot(dir, "06b-dragged")
                Engine.note("after drag: panel c at \(figure?.element("2")?.box.minX ?? -1)")
                undoEdit(nil); await settle()
            }
            canvas.selection = ["0", "1", "2"]
            await settle(); shot(dir, "06-multi")
            canvas.selection = ["6"]
            await settle(); shot(dir, "07-text")
            showProblems(nil)
            await settle(); shot(dir, "08-preflight")
            showTerminal(nil)
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            shot(dir, "09-terminal")
            canvas.selection = []
            await settle(); shot(dir, "10-nothing-selected")
            NSApp.terminate(nil)
        }
    }

    /// A patchwork layout (open the project at its figure file): a panel in it, a gap dragged, the dark version.
    private func layoutShots(_ dir: String) async {
        shot(dir, "L1-layout")
        canvas.selection = ["0.3"]
        await settle(); shot(dir, "L2-child")
        if let l = figure?.element("0"), let k = l.dividers.firstIndex(where: { $0.vertical && $0.editable }) {
            let d = l.dividers[k]
            let start = CGPoint(x: d.at, y: (d.from + d.to) / 2)
            mouse(.leftMouseDown, start)
            for i in 1...12 { mouse(.leftMouseDragged, CGPoint(x: start.x + CGFloat(i), y: start.y)) }
            shot(dir, "L3-dragging-gap")
            mouse(.leftMouseUp, CGPoint(x: start.x + 12, y: start.y))
            await settle(); shot(dir, "L4-gap-dragged")
            Engine.note("layout widths now \(figure?.element("0")?.props["widths"] ?? "none")")
            undoEdit(nil); await settle()
        }
        canvas.selection = ["0"]
        toggleDarkPreview(nil)
        await settle(); try? await Task.sleep(nanoseconds: 1_000_000_000); shot(dir, "L5-dark-version")
        toggleDarkPreview(nil)
        await settle()
        NSApp.terminate(nil)
    }

    /// Figure 3 (open the project at fig3.py): retyping a panel's text, cropping, the pen, copy and paste, layers.
    private func featureShots(_ dir: String) async {
        func src() -> String { (try? String(contentsOfFile: figure?.file ?? "", encoding: .utf8)) ?? "" }
        shot(dir, "F1-figure")
        canvas.selection = ["4"]
        await settle(); shot(dir, "F2-panel-texts")
        if let t = figure?.element("4")?.texts.first(where: { $0.key == "ax0.xlabel" }) {
            mouse(.leftMouseDown, CGPoint(x: t.box.midX, y: t.box.midY), clicks: 2)
            shot(dir, "F3-retyping")
            canvas.typeInEditor("UMAP 1")
            await settle(); shot(dir, "F4-retyped")
            Engine.note("retyped: \(src().contains("\"ax0.xlabel\": \"UMAP 1\""))")
        }
        canvas.selection = ["0"]
        canvas.beginCrop("0")
        if let b = figure?.element("0")?.box {
            let h = CGPoint(x: b.maxX, y: b.midY)
            mouse(.leftMouseDown, h)
            for i in 1...15 { mouse(.leftMouseDragged, CGPoint(x: h.x - CGFloat(i), y: h.y)) }
            shot(dir, "F5-cropping")
            mouse(.leftMouseUp, CGPoint(x: h.x - 15, y: h.y))
            await settle(); canvas.endCrop(); shot(dir, "F6-cropped")
            Engine.note("cropped: \(src().components(separatedBy: "\n").first { $0.hasPrefix("cells =") } ?? "?")")
        }
        canvas.selection = []
        canvas.tool = .pen
        for (i, q) in [CGPoint(x: 20, y: 85), CGPoint(x: 35, y: 78), CGPoint(x: 50, y: 88)].enumerated() {
            mouse(.leftMouseDown, q, clicks: i == 2 ? 2 : 1); mouse(.leftMouseUp, q)
        }
        await settle(); shot(dir, "F7-pen")
        Engine.note("pen: \(src().components(separatedBy: "\n").first { $0.hasPrefix("fig.path([(20") } ?? "none")")
        canvas.selection = ["6"]
        copy(nil); await settle()
        paste(nil); await settle()
        Engine.note("arrows after paste: \(src().components(separatedBy: "fig.arrow(").count - 1)")
        setLayer("5", locked: true); await settle()
        setLayer("8", hidden: true); await settle()
        canvas.selection = ["5"]
        showHistory(nil)
        await settle(); shot(dir, "F8-history-layers")
        Engine.note("locked: \(src().contains("width=78, locked=True")), hidden: \(src().contains("rotation=90, hidden=True"))")
        NSApp.terminate(nil)
    }

    /// The Code tab following the selection (open the project at fig1.py).
    private func codeShots(_ dir: String) async {
        await settle()
        shot(dir, "C1-figure-code")
        canvas.selection = ["1"]
        await settle(); shot(dir, "C2-panel-code")
        Engine.note("panel: \(code.path ?? "-") line \(code.textView.selectedRange().location)")
        canvas.selection = ["6"]
        await settle(); shot(dir, "C3-text-line")
        Engine.note("text: \(code.path ?? "-")")
        canvas.selection = []
        await settle()
        Engine.note("none: \(code.path ?? "-")")
        NSApp.terminate(nil)
    }

    /// Colours (open the project at fig1.py): a panel's colours, the colour-vision preview, recolouring, a palette.
    private func colorShots(_ dir: String) async {
        canvas.selection = ["5"]
        await settle(); shot(dir, "K1-panel-colours")
        canvas.vision = "deuteranopia"
        await settle(); shot(dir, "K2-deuteranopia")
        canvas.vision = "normal"
        edit(["op": "panel_color", "oid": "5", "keys": ["ax0.patch2", "ax0.patch3"], "color": "#0072B2", "old": "#D1495B"])
        await settle(); shot(dir, "K3-recoloured")
        canvas.selection = []
        edit(["op": "style", "props": ["palette": "okabe-ito"]])
        await settle(); shot(dir, "K4-okabe-ito")
        Engine.note("warnings now: \(figure?.warnings.map(\.message) ?? [])")
        NSApp.terminate(nil)
    }

    /// Wait for the engine work queued so far, then a moment for drawing.
    /// Texts and marks of a panel picked by clicking, the figure copied as a picture, a scrolled canvas, BioCartoon.
    private func partShots(_ dir: String) async {
        // scrolled far down: the figure must stay under the tool bar and the rulers
        for _ in 0..<12 {
            if let e = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 2, wheel1: -10, wheel2: 0, wheel3: 0).flatMap(NSEvent.init(cgEvent:)) {
                canvas.scrollWheel(with: e)
            }
        }
        await settle(); shot(dir, "P0-scrolled")
        canvas.fit(); await settle()
        // one click on the scatter panel's x-axis label picks the panel and the label
        guard let sc = figure?.element("1"), let xl = sc.texts.first(where: { $0.key == "ax0.xlabel" }) else { Engine.note("parts: no label"); NSApp.terminate(nil); return }
        mouse(.leftMouseDown, CGPoint(x: xl.box.midX, y: xl.box.midY)); mouse(.leftMouseUp, CGPoint(x: xl.box.midX, y: xl.box.midY))
        await settle(); shot(dir, "P1-text-picked")
        Engine.note("parts: selection \(canvas.selection) part \(String(describing: canvas.part))")
        edit(["op": "panel_text_style", "oid": "1", "key": "ax0.xlabel", "text": xl.text, "props": ["size": 9, "color": "#D55E00", "weight": "bold"]])
        await settle(); shot(dir, "P2-text-restyled")
        Engine.note("parts: after restyle \(figure?.element("1")?.texts.first { $0.key == "ax0.xlabel" }.map { "\($0.size) \($0.color ?? "-") bold \($0.bold)" } ?? "-") part \(String(describing: canvas.part))")
        undoEdit(nil); await settle()
        // a bar of the bars panel
        if let bars = figure?.element("5"), let mk = bars.marks.first(where: { $0.key == "ax0.patch1" }) {
            canvas.selection = []
            mouse(.leftMouseDown, CGPoint(x: mk.box.midX, y: mk.box.midY)); mouse(.leftMouseUp, CGPoint(x: mk.box.midX, y: mk.box.midY))
            await settle(); shot(dir, "P3-mark-picked")
            Engine.note("parts: mark \(String(describing: canvas.part))")
        }
        canvas.part = nil; canvas.selection = []
        // the whole figure on the pasteboard
        copyFigure(nil)
        await settle()
        let types = NSPasteboard.general.types?.map(\.rawValue) ?? []
        Engine.note("copy figure: \(types) pdf \(NSPasteboard.general.data(forType: .pdf)?.count ?? 0) png \(NSPasteboard.general.data(forType: .png)?.count ?? 0)")
        if let d = NSPasteboard.general.data(forType: .png) { try? d.write(to: URL(fileURLWithPath: dir).appendingPathComponent("P4-copied.png")) }
        // BioCartoon: the search in the inspector's place, an icon dropped on the figure
        showBioCartoon(nil)
        for _ in 0..<300 where (biocartoonPane?.resultCount ?? 0) == 0 && biocartoonPane?.offersInstall == nil { try? await Task.sleep(nanoseconds: 100_000_000) }
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        shot(dir, "P5-biocartoon")
        Engine.note("biocartoon: exe \(biocartoonPane?.exe ?? "-") results \(biocartoonPane?.resultCount ?? 0) offers \(biocartoonPane?.offersInstall ?? "-")")
        var vf = BCFilter(); vf.fileTypes = ["svg"]
        for (q, filter) in [("mitochondria", BCFilter()), ("neuron", vf)] {
            guard let exe = biocartoonPane?.exe, let icon = try? await BioCartoonCLI.search(exe, query: q, filter: filter, sort: "relevance", offset: 0, limit: 1).first,
                  let data = try? JSONEncoder().encode(icon) else { Engine.note("biocartoon: no \(q)"); continue }
            let n = figure?.elements.count ?? 0
            _ = biocartoonDropped(data, at: CGPoint(x: q == "neuron" ? 150 : 100, y: 90))
            for _ in 0..<200 where (figure?.elements.count ?? 0) == n { try? await Task.sleep(nanoseconds: 100_000_000) }
            await settle()
            if let e = figure?.elements.last {
                let src = e.s("source") ?? "-"
                Engine.note("biocartoon: \(icon.id) svg \(icon.svg_key != nil) -> \(e.kind) \(src) box \(e.box) error \(e.error ?? "none") origin \(BioCartoonCLI.origin(ofImageAt: (project ?? "") + "/" + src)?.id ?? "-")")
                canvas.selection = [e.oid]
                Engine.note("biocartoon: menu \(contextMenu().items.map(\.title))")
            }
        }
        canvas.selection = []
        await settle(); shot(dir, "P6-icons-placed")
        hideBioCartoon()
        await settle(); shot(dir, "P7-inspector-back")
        NSApp.terminate(nil)
    }

    private func settle() async {
        try? await Task.sleep(nanoseconds: 300_000_000)
        await waitForQueue()
        try? await Task.sleep(nanoseconds: 300_000_000)
    }

    /// A mouse event at a figure point (mm), sent to the canvas.
    private func mouse(_ type: NSEvent.EventType, _ p: CGPoint, clicks: Int = 1) {
        let w = canvas.convert(canvas.toView(p), to: nil)
        guard let e = NSEvent.mouseEvent(with: type, location: w, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                         windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: clicks, pressure: 1) else { return }
        switch type {
        case .leftMouseDown: canvas.mouseDown(with: e)
        case .leftMouseDragged: canvas.mouseDragged(with: e)
        default: canvas.mouseUp(with: e)
        }
    }

    private func shot(_ dir: String, _ name: String) {
        guard let v = window.contentView, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { return }
        v.cacheDisplay(in: v.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
        Engine.note("shot \(name)")
    }
}
