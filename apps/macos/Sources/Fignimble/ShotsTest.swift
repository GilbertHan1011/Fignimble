import AppKit

/// A scripted walk through the editor that saves pictures of the window, for checking the UI without a person
/// (after Manimble's ShotsTest): `FIGNIMBLE_SHOTS=/some/folder Fignimble.app/Contents/MacOS/Fignimble <project>`.
/// It edits the project it is given, so give it a copy.
extension MainController {
    func runShotsIfAsked() {
        guard let dir = ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS"] else { return }
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        Task { @MainActor in
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "blank" { await blankShots(dir); return }
            // with FIGNIMBLE_TEST_SETUP the Python is set up first, which takes a while
            let wait = ProcessInfo.processInfo.environment["FIGNIMBLE_TEST_SETUP"] != nil ? 3000 : 300
            for _ in 0..<wait where figure == nil { try? await Task.sleep(nanoseconds: 100_000_000) }
            try? await Task.sleep(nanoseconds: 800_000_000)
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "layout" { await layoutShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "features" { await featureShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "code" { await codeShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "colors" { await colorShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "parts" { await partShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "more" { await moreShots(dir); return }
            if ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS_SCENE"] == "size" { await sizeShots(dir); return }
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

    /// The export dialog, no panel letters, a table and its Word file, a panel from an SSH server
    /// (FIGNIMBLE_SSH: a stand-in for ssh), Update from Server.
    private func moreShots(_ dir: String) async {
        exportFigure(nil)
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        // the save panel itself is drawn by another process: the options Fignimble adds to it
        if let sheet = window.attachedSheet, let v = (sheet as? NSSavePanel)?.accessoryView, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: dir).appendingPathComponent("M1-export-dialog.png"))
            window.endSheet(sheet)
        }
        labelsNone(nil)
        await settle(); shot(dir, "M2-no-letters")
        Engine.note("more: labels after No Letters \(figure?.labels.count ?? -1)")
        labelsNone(nil); await settle()
        Engine.note("more: labels back \(figure?.labels.count ?? -1)")
        // a table from a CSV, then as Word
        let csv = URL(fileURLWithPath: dir).appendingPathComponent("genes.csv")
        try? "Gene,Cells,Fold change\nCD3E,1204,2.4512\nLYZ,2950,1.10\n".write(to: csv, atomically: true, encoding: .utf8)
        importFiles([csv], at: CGPoint(x: 100, y: 88))
        await settle()
        if let t = figure?.elements.last, t.kind == "table" {
            canvas.selection = [t.oid]
            await settle(); shot(dir, "M3-table")
            let out = dir + "/genes.docx"
            let r = (try? await engine.json("export_table", ["figure": current ?? "", "oid": t.oid, "path": out])) ?? [:]
            Engine.note("more: table \(t.title(label: nil)) box \(t.box) docx \(r["ok"] ?? "-") \(FileManager.default.fileExists(atPath: out)) menu \(contextMenu().items.map(\.title).filter { $0.contains("Word") })")
        } else { Engine.note("more: no table") }
        // the SSH dialog lists a folder on the "server"
        canvas.selection = []
        let d = RemoteDialog(main: self)
        var fetched: (String, String)?
        d.onImport = { h, p in fetched = (h, p) }
        d.begin()
        try? await Task.sleep(nanoseconds: 800_000_000)
        if let host = d.panel.contentView?.firstDescendant(NSComboBox.self) { host.stringValue = "lab-server" }
        if let field = d.panel.contentView?.descendants(NSTextField.self).first(where: { $0.placeholderString?.hasPrefix("folder") == true }) { field.stringValue = "~/analysis" }
        d.list()
        try? await Task.sleep(nanoseconds: 2_500_000_000)
        if let v = d.panel.contentView, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: dir).appendingPathComponent("M4-ssh-dialog.png"))
        }
        if let table = d.panel.contentView?.firstDescendant(NSTableView.self), let i = (0..<table.numberOfRows).first(where: { r in
            (table.view(atColumn: 0, row: r, makeIfNecessary: true)?.descendants(NSTextField.self).first?.stringValue ?? "").hasSuffix(".py") }) {
            table.selectRowIndexes([i], byExtendingSelection: false)
            d.perform(Selector(("doImport")))
        }
        Engine.note("more: dialog chose \(fetched.map { "\($0.0):\($0.1)" } ?? "nothing")")
        window.attachedSheet.map { window.endSheet($0) }
        if let (h, p) = fetched, let name = current {
            let r = (try? await engine.json("import_remote", ["figure": name, "host": h, "path": p, "x": 60.0, "y": 60.0, "pxPerMM": lastPx])) ?? [:]
            if let fig = r["figure"] as? [String: Any] { apply(fig) }
            if let sel = r["select"] as? [String] { canvas.selection = sel }
            await settle(); shot(dir, "M5-remote-panel")
            let e = canvas.selection.first.flatMap { figure?.element($0) }
            Engine.note("more: import \(r["ok"] ?? "-") \(r["error"] ?? "") origin \(e.flatMap { remoteOrigin(of: $0) } ?? "-") error \(e?.error ?? "none") menu \(contextMenu().items.map(\.title).filter { $0.contains("Server") })")
        }
        NSApp.terminate(nil)
    }

    /// How wide the window has to be: its frame, the screen's, the narrowest the tool bar allows; then 1280 x 780.
    private func sizeShots(_ dir: String) async {
        func report(_ what: String) {
            let bar = window.contentView?.descendants(NSStackView.self).first { $0.arrangedSubviews.contains { $0 is NSSegmentedControl } }
            Engine.note("size \(what): window \(Int(window.frame.width))x\(Int(window.frame.height)), screen visible \(Int(window.screen?.visibleFrame.width ?? 0))x\(Int(window.screen?.visibleFrame.height ?? 0)), "
                + "tool bar needs \(Int(bar?.fittingSize.width ?? -1)), navigator \(Int(navigator.frame.width)), inspector \(Int(rightHost.frame.width)), canvas \(Int(canvas.frame.width))")
        }
        report("at launch")
        window.setFrame(NSRect(x: 0, y: 0, width: 1280, height: 780), display: true)
        await settle(); report("asked 1280x780"); shot(dir, "S1-1280")
        window.setFrame(NSRect(x: 0, y: 0, width: 1100, height: 700), display: true)
        await settle(); report("asked 1100x700"); shot(dir, "S2-1100")
        NSApp.terminate(nil)
    }

    /// Started with no project: the empty window, File ▸ Open Recent, then a recent project opened from it.
    private func blankShots(_ dir: String) async {
        try? await Task.sleep(nanoseconds: 4_000_000_000)
        shot(dir, "B1-empty")
        let file = NSApp.mainMenu?.items.first { $0.title == "File" }?.submenu
        let recent = file?.items.first { $0.title == "Open Recent" }
        if let m = recent?.submenu { m.delegate?.menuNeedsUpdate?(m) }
        Engine.note("blank: project \(project ?? "none") figure \(figure?.name ?? "none"); Open Recent: \(recent?.submenu?.items.map(\.title) ?? ["missing"])")
        if let first = recent?.submenu?.items.first, first.action != nil {
            openRecent(first)
            for _ in 0..<100 where figure == nil { try? await Task.sleep(nanoseconds: 100_000_000) }
            await settle(); shot(dir, "B2-opened-recent")
            Engine.note("blank: opened \(project ?? "none") figure \(figure?.name ?? "none")")
        }
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

private extension NSView {
    func descendants<T: NSView>(_ type: T.Type) -> [T] {
        subviews.flatMap { ($0 as? T).map { [$0] } ?? [] } + subviews.flatMap { $0.descendants(type) }
    }
    func firstDescendant<T: NSView>(_ type: T.Type) -> T? { descendants(type).first }
}
