import AppKit
import UniformTypeIdentifiers

/// The window: figures on the left, the canvas with its rulers in the middle (the code, preflight and terminals in
/// the drawer under it), the inspector on the right. Every edit goes to the engine, which changes the code and
/// renders the figure again.
@MainActor
final class MainController: NSObject, NSWindowDelegate, NSMenuItemValidation {
    let window: NSWindow
    let engine = Engine()
    let canvas = CanvasView()
    let inspector = Inspector()
    let navigator = Navigator()
    let code = CodePane()
    let problems = ProblemsView()
    let history = HistoryView()
    let terminal = TerminalPanel()
    private(set) var drawer: BottomDrawer!
    private let hRuler = RulerView(horizontal: true)
    private let vRuler = RulerView(horizontal: false)
    private let pill = Pill()
    private let status = NSTextField(labelWithString: "")
    private let zoomLabel = NSTextField(labelWithString: "")
    private let toolControl = NSSegmentedControl()
    private var root = GrabSplitView()
    private var middle = GrabSplitView()

    private(set) var project: String?
    private(set) var current: String?
    private(set) var figure: FigureData?
    private(set) var figures: [[String: Any]] = []
    private(set) var journals: [String: [String: Any]] = [:]
    private var state: [String: Any] = [:]
    var alignTo = "selection"
    /// The canvas shows the figure's dark version.
    private(set) var darkPreview = false
    private var python: String?
    private var queue: Task<Void, Never>?
    private var nudgeTotal = CGPoint.zero
    private var nudgeWork: DispatchWorkItem?
    private var lastPx: Double = 12
    /// The look copied by Copy Style, for Paste Style.
    private var copiedStyle: [String: Any]?
    static let pasteType = NSPasteboard.PasteboardType("org.pachterlab.fignimble.code")
    private var drawerHeight: CGFloat = 260

    override init() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        super.init()
        window.title = "Fignimble"
        window.delegate = self
        window.minSize = NSSize(width: 900, height: 560)
        window.setFrameAutosaveName("FignimbleMain")
        build()
    }

    // MARK: layout

    private func build() {
        canvas.main = self; inspector.main = self; navigator.main = self; code.main = self; problems.main = self; history.main = self
        hRuler.canvas = canvas; vRuler.canvas = canvas
        drawer = BottomDrawer(code: code, problems: problems, history: history, terminal: terminal)
        drawer.onShowTerminal = { [weak self] in self?.showTerminal(nil) }
        drawer.onNewTerminal = { [weak self] in self?.newTerminal(nil) }
        drawer.onHide = { [weak self] in self?.setDrawer(visible: false) }
        terminal.onHide = { [weak self] in self?.drawer.show(.code) }
        canvas.onCursor = { [weak self] p in self?.cursorMoved(p) }
        canvas.onViewChange = { [weak self] in self?.viewChanged() }

        // the canvas area: a tool bar, the rulers, the canvas, a status line
        let area = NSView()
        area.wantsLayer = true
        Theme.layerColors(area) { $0.layer?.backgroundColor = Theme.barBackground.cgColor }
        let bar = toolbar()
        let corner = NSView(); corner.wantsLayer = true
        Theme.layerColors(corner) { $0.layer?.backgroundColor = Theme.barBackground.cgColor }
        status.font = Theme.font(10.5); status.textColor = Theme.ink(0.55); status.lineBreakMode = .byTruncatingMiddle
        // a long path gives way rather than widening the window
        status.setContentCompressionResistancePriority(.init(100), for: .horizontal)
        pill.defaultEstimate = 1.5
        for v in [bar, corner, hRuler, vRuler, canvas, status, pill] as [NSView] { v.translatesAutoresizingMaskIntoConstraints = false; area.addSubview(v) }
        let t = RulerView.thickness
        NSLayoutConstraint.activate([
            bar.leadingAnchor.constraint(equalTo: area.leadingAnchor), bar.trailingAnchor.constraint(equalTo: area.trailingAnchor),
            bar.topAnchor.constraint(equalTo: area.topAnchor), bar.heightAnchor.constraint(equalToConstant: 36),
            corner.leadingAnchor.constraint(equalTo: area.leadingAnchor), corner.topAnchor.constraint(equalTo: bar.bottomAnchor),
            corner.widthAnchor.constraint(equalToConstant: t), corner.heightAnchor.constraint(equalToConstant: t),
            hRuler.leadingAnchor.constraint(equalTo: corner.trailingAnchor), hRuler.trailingAnchor.constraint(equalTo: area.trailingAnchor),
            hRuler.topAnchor.constraint(equalTo: bar.bottomAnchor), hRuler.heightAnchor.constraint(equalToConstant: t),
            vRuler.leadingAnchor.constraint(equalTo: area.leadingAnchor), vRuler.topAnchor.constraint(equalTo: corner.bottomAnchor),
            vRuler.widthAnchor.constraint(equalToConstant: t), vRuler.bottomAnchor.constraint(equalTo: status.topAnchor),
            canvas.leadingAnchor.constraint(equalTo: vRuler.trailingAnchor), canvas.trailingAnchor.constraint(equalTo: area.trailingAnchor),
            canvas.topAnchor.constraint(equalTo: hRuler.bottomAnchor), canvas.bottomAnchor.constraint(equalTo: status.topAnchor),
            status.leadingAnchor.constraint(equalTo: area.leadingAnchor, constant: 8), status.trailingAnchor.constraint(equalTo: area.trailingAnchor, constant: -8),
            status.bottomAnchor.constraint(equalTo: area.bottomAnchor, constant: -3), status.heightAnchor.constraint(equalToConstant: 16),
            pill.centerXAnchor.constraint(equalTo: canvas.centerXAnchor), pill.topAnchor.constraint(equalTo: canvas.topAnchor, constant: 12),
            pill.widthAnchor.constraint(lessThanOrEqualTo: canvas.widthAnchor, multiplier: 0.8),
        ])

        middle.isVertical = false; middle.dividerStyle = .thin; middle.collapsesLastPane = true
        middle.addArrangedSubview(area); middle.addArrangedSubview(drawer)
        middle.setHoldingPriority(.init(260), forSubviewAt: 0); middle.setHoldingPriority(.init(270), forSubviewAt: 1)
        root.isVertical = true; root.dividerStyle = .thin
        root.addArrangedSubview(navigator); root.addArrangedSubview(middle); root.addArrangedSubview(inspector)
        root.setHoldingPriority(.init(270), forSubviewAt: 0); root.setHoldingPriority(.init(250), forSubviewAt: 1); root.setHoldingPriority(.init(270), forSubviewAt: 2)
        window.contentView = root
        DispatchQueue.main.async { [self] in
            root.setPosition(210, ofDividerAt: 0)
            root.setPosition(root.bounds.width - 270, ofDividerAt: 1)
            middle.setPosition(middle.bounds.height - drawerHeight, ofDividerAt: 0)
        }
        inspector.update()
    }

    private func toolbar() -> NSView {
        let bar = NSView(); bar.wantsLayer = true
        Theme.layerColors(bar) { $0.layer?.backgroundColor = Theme.barBackground.cgColor }
        toolControl.segmentCount = Tool.allCases.count
        toolControl.trackingMode = .selectOne
        for (i, t) in Tool.allCases.enumerated() {
            toolControl.setImage(NSImage(systemSymbolName: t.symbol, accessibilityDescription: t.title), forSegment: i)
            toolControl.setToolTip("\(t.title) (\(t.key.uppercased()))", forSegment: i)
            toolControl.setWidth(30, forSegment: i)
        }
        toolControl.selectedSegment = 0; toolControl.target = self; toolControl.action = #selector(toolPicked)
        toolControl.controlSize = .regular; toolControl.segmentStyle = .texturedRounded
        func b(_ sym: String, _ tip: String, _ sel: Selector) -> NSButton {
            let x = NSButton(image: NSImage(systemSymbolName: sym, accessibilityDescription: tip) ?? NSImage(), target: self, action: sel)
            x.bezelStyle = .texturedRounded; x.toolTip = tip; return x
        }
        func sep() -> NSView { let v = NSBox(); v.boxType = .separator; v.widthAnchor.constraint(equalToConstant: 1).isActive = true; v.heightAnchor.constraint(equalToConstant: 18).isActive = true; return v }
        let panel = NSButton(title: "Panel", image: NSImage(systemSymbolName: "chart.xyaxis.line", accessibilityDescription: nil)!, target: self, action: #selector(newPanel(_:)))
        panel.bezelStyle = .texturedRounded; panel.toolTip = "New panel drawn by Python code (⇧⌘P)"
        let image = NSButton(title: "Picture", image: NSImage(systemSymbolName: "photo", accessibilityDescription: nil)!, target: self, action: #selector(insertImage(_:)))
        image.bezelStyle = .texturedRounded; image.toolTip = "Place a picture: PNG, TIFF, JPEG, PDF or SVG (⇧⌘I)"
        let aligns: [(String, String, Selector)] = [("align.horizontal.left", "Align left edges", #selector(alignLeft(_:))),
                                                    ("align.horizontal.center", "Align centres", #selector(alignCenter(_:))),
                                                    ("align.horizontal.right", "Align right edges", #selector(alignRight(_:))),
                                                    ("align.vertical.top", "Align tops", #selector(alignTop(_:))),
                                                    ("align.vertical.center", "Align middles", #selector(alignMiddle(_:))),
                                                    ("align.vertical.bottom", "Align bottoms", #selector(alignBottom(_:))),
                                                    ("distribute.horizontal.center", "Distribute horizontally", #selector(distributeH(_:))),
                                                    ("distribute.vertical.center", "Distribute vertically", #selector(distributeV(_:)))]
        let alignStack = NSStackView(views: aligns.map { b($0.0, $0.1, $0.2) } + [b("rectangle.split.2x2", "Make a layout of the selected panels (⌘L): rows and columns, plot areas lined up", #selector(makeLayout(_:)))])
        alignStack.spacing = 2
        zoomLabel.font = Theme.mono(10.5); zoomLabel.textColor = Theme.ink(0.6); zoomLabel.alignment = .center
        zoomLabel.widthAnchor.constraint(equalToConstant: 46).isActive = true
        let spacer = NSView(); spacer.setContentHuggingPriority(.init(1), for: .horizontal)
        let row = NSStackView(views: [toolControl, sep(), panel, image, sep(), alignStack, spacer,
                                      b("minus.magnifyingglass", "Zoom out (⌘-)", #selector(zoomOut(_:))), zoomLabel,
                                      b("plus.magnifyingglass", "Zoom in (⌘+)", #selector(zoomIn(_:))),
                                      b("arrow.up.left.and.down.right.magnifyingglass", "Fit the figure (⌘0)", #selector(zoomFit(_:))), sep(),
                                      b("moon", "Dark version of the figure, for talks (⌥⌘D)", #selector(toggleDarkPreview(_:))),
                                      b("chevron.left.forwardslash.chevron.right", "The code of the figure and of what is selected (⌥⌘C)", #selector(showCodePane(_:))),
                                      b("terminal", "Terminal for a coding agent (⌥⌘T)", #selector(showTerminal(_:))),
                                      b("square.and.arrow.up", "Export the figure (⌘E)", #selector(exportFigure(_:)))])
        row.spacing = 8; row.alignment = .centerY
        row.translatesAutoresizingMaskIntoConstraints = false
        bar.addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: bar.leadingAnchor, constant: 10), row.trailingAnchor.constraint(equalTo: bar.trailingAnchor, constant: -10),
            row.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
        ])
        return bar
    }

    func showWindow() { window.makeKeyAndOrderFront(nil); if window.frame.origin == .zero { window.center() } }

    // MARK: engine

    func start(open url: URL?) {
        Task {
            let found = await Task.detached { Engine.findPython() }.value
            guard let py = found else { missingPython(); return }
            python = py
            TerminalSession.python = py
            do { try engine.start(python: py) } catch { alert("Couldn't start the engine", error.localizedDescription); return }
            engine.onEvent = { [weak self] e in self?.event(e) }
            engine.onExit = { [weak self] code in
                self?.alert("The Fignimble engine stopped", "Exit status \(code). The end of its log (~/Library/Logs/fignimble.log):\n\n" + Engine.logTail())
            }
            if let j = try? await engine.json("journals") { journals = j.compactMapValues { $0 as? [String: Any] } }
            runShotsIfAsked()
            if let u = url { openProject(at: u) }
            else if let last = UserDefaults.standard.string(forKey: "lastProject"), FileManager.default.fileExists(atPath: last) {
                openProject(at: URL(fileURLWithPath: last))
            } else { inspector.update(); status.stringValue = "Open a project (⌘O) or make a new one (⇧⌘N)." }
        }
    }

    private func missingPython() {
        let a = NSAlert()
        a.messageText = "Fignimble needs Python with matplotlib and PyMuPDF"
        a.informativeText = "Run install_fignimble.sh in the Fignimble folder, or install them into a Python of your own:\n\npython3 -m pip install matplotlib pymupdf pillow numpy\n\nthen open Fignimble again. (Fignimble looks at $FIGNIMBLE_PYTHON, ~/Library/Application Support/Fignimble/python, the checkout's .venv and the Pythons on your PATH.)"
        a.addCopyButton()
        a.runModal()
    }

    private func event(_ e: [String: Any]) {
        switch e["event"] as? String {
        case "changed":
            code.reloadIfChanged()
            refresh()
        case "rendered":
            Task { await refreshState() }
        default: break
        }
    }

    /// Until the engine work queued so far is done.
    func waitForQueue() async { await queue?.value }

    /// Run engine work one piece at a time, in order.
    private func enqueue(_ work: @escaping @MainActor () async -> Void) {
        let prev = queue
        queue = Task { @MainActor in
            await prev?.value
            await work()
        }
    }

    func openProject(at url: URL) {
        var dir = url, fig: String?
        var isDir: ObjCBool = false
        FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir)
        if !isDir.boolValue { dir = url.deletingLastPathComponent(); fig = url.deletingPathExtension().lastPathComponent }
        if code.dirty { code.save() }
        enqueue { [self] in
            do {
                let r = try await engine.json("open", ["project": dir.path])
                project = r["project"] as? String ?? dir.path
            } catch { alert("Couldn't open \(dir.lastPathComponent)", error.localizedDescription); return }
            UserDefaults.standard.set(project, forKey: "lastProject")
            NSDocumentController.shared.noteNewRecentDocumentURL(dir)
            window.title = "Fignimble — " + dir.lastPathComponent
            window.representedURL = dir
            current = nil; figure = nil
            canvas.selection = []
            await refreshState()
            if terminal.hasStarted { terminal.start(in: dir.path, original: nil) }
            let name = fig ?? (figures.first?["name"] as? String)
            if let n = name { await load(n) } else { canvas.setFigure(nil); inspector.update(); status.stringValue = "No figures yet: File ▸ New Figure (⌘N)." }
            explainProjectOnce()
        }
    }

    /// The first time a project is opened: where its code is, and that edits go straight into it.
    private func explainProjectOnce() {
        guard let p = project, ProcessInfo.processInfo.environment["FIGNIMBLE_SHOTS"] == nil else { return }
        var seen = UserDefaults.standard.stringArray(forKey: "explainedProjects") ?? []
        guard !seen.contains(p) else { return }
        seen.append(p)
        UserDefaults.standard.set(seen, forKey: "explainedProjects")
        let fig = figure.map { ($0.file as NSString).lastPathComponent } ?? "the figure files"
        let a = NSAlert()
        a.messageText = "Your figures are Python code"
        a.informativeText = "This figure is \(fig) in\n\((p as NSString).abbreviatingWithTildeInPath)\n\n"
            + "Everything you do here (moving, resizing, retyping, styling) is written into that code straight away; there is "
            + "nothing to save. The Code tab (⌥⌘C) shows the code of whatever you select: a panel's own drawing code, or the "
            + "figure's line that places it. Agents in the terminal edit the same files."
        a.addButton(withTitle: "Got It")
        a.addButton(withTitle: "Show in Finder")
        a.beginSheetModal(for: window) { r in
            if r == .alertSecondButtonReturn { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: self.figure?.file ?? p)]) }
        }
    }

    func refreshState() async {
        guard project != nil, let s = try? await engine.json("state") else { return }
        state = s
        figures = s["figures"] as? [[String: Any]] ?? []
        history.set(done: s["history"] as? [String] ?? [], undone: s["future"] as? [String] ?? [])
        navigator.setFigures(figures, current: current)
        var files: [String] = []
        if let f = figure?.file, !f.isEmpty { files.append(f) }
        if let p = project { files.append(p + "/style.py") }
        files += (s["panels"] as? [String] ?? []).map { project! + "/" + $0 }
        code.setFiles(files.filter { FileManager.default.fileExists(atPath: $0) })
    }

    private func load(_ name: String) async {
        busy("Rendering \(name)…")
        do {
            let r = try await engine.json("figure", ["name": name, "pxPerMM": canvas.wantedPxPerMM, "dark": darkPreview])
            lastPx = canvas.wantedPxPerMM
            let switched = current != name
            current = name
            apply(r)
            if switched, let f = figure, !f.file.isEmpty { code.open(f.file, line: nil) }
            idle()
        } catch { idle(); toast(error.localizedDescription, error: true) }
        await refreshState()
    }

    /// Show a figure from the list.
    func show(figure name: String) {
        guard name != current else { return }
        if code.dirty { code.save() }
        canvas.selection = []
        enqueue { [self] in await load(name) }
    }

    /// Render the figure on screen again (its files changed, or the zoom needs sharper pictures).
    func refresh(force: Bool = false) {
        guard let name = current else { Task { await refreshState() }; return }
        enqueue { [self] in await load(name) }
    }

    private func apply(_ r: [String: Any]) {
        let f = FigureData(r)
        figure = f
        canvas.setFigure(f)
        navigator.setLayers(f, selection: canvas.selection)
        problems.set(f.warnings)
        drawer.rebuildStrip()
        inspector.update()
        hRuler.needsDisplay = true; vRuler.needsDisplay = true
        if let err = f.error {
            status.stringValue = "The figure's code doesn't run: " + (err.split(separator: "\n").last.map(String.init) ?? "")
        } else {
            let n = f.warnings.filter { $0.level != "info" }.count
            let where_ = (f.file as NSString).abbreviatingWithTildeInPath
            status.stringValue = where_ + "  ·  \(mm(Double(f.size.width))) × \(mm(Double(f.size.height))) mm" + (f.journal.map { "  ·  \($0["name"] as? String ?? "")" } ?? "")
                + (n > 0 ? "  ·  \(n) preflight warning\(n == 1 ? "" : "s")" : "")
        }
        updateZoomLabel()
    }

    /// An edit of the figure on screen: `args` for the engine's `edit` (op and its arguments).
    func edit(_ args: [String: Any]) {
        guard let name = current else { return }
        var a = args
        a["figure"] = name
        a["pxPerMM"] = lastPx
        enqueue { [self] in
            busy(nil)
            do {
                let r = try await engine.json("edit", a)
                if let f = r["figure"] as? [String: Any] { apply(f) }
                if r["ok"] as? Bool == true {
                    if let sel = r["select"] as? [String], !sel.isEmpty { canvas.selection = sel; navigator.selectLayers(sel) }
                    idle()
                } else {
                    canvas.clearPending()
                    toast(r["error"] as? String ?? "That didn't work", error: true)
                }
            } catch { canvas.clearPending(); toast(error.localizedDescription, error: true) }
            code.reloadIfChanged()
            await refreshState()
        }
    }

    func writeSource(_ path: String, _ text: String, done: @escaping () -> Void) {
        enqueue { [self] in
            busy("Applying the code…")
            do {
                var a: [String: Any] = ["file": path, "text": text, "pxPerMM": lastPx]
                if let c = current { a["figure"] = c }
                let r = try await engine.json("write_source", a)
                if let f = r["figure"] as? [String: Any] { apply(f) }
                idle()
                done()
            } catch { toast(error.localizedDescription, error: true) }
            await refreshState()
        }
    }

    // MARK: messages

    private var busyShown = false
    private func busy(_ text: String?) {
        busyShown = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            guard let self, self.busyShown else { return }
            self.pill.show(text ?? "Rendering…", symbol: nil, tint: nil, spinning: true, cancellable: false)
        }
    }
    private func idle() { busyShown = false; pill.hide() }
    func toast(_ text: String, error: Bool = false) {
        busyShown = false
        pill.show(text, symbol: error ? "exclamationmark.triangle.fill" : "checkmark.circle.fill", tint: error ? .systemOrange : .systemGreen)
        let t = text
        DispatchQueue.main.asyncAfter(deadline: .now() + (error ? 6 : 2.5)) { [weak self] in
            guard let self, self.pill.label.stringValue == t, !self.pill.hovered else { return }
            self.pill.hide()
        }
    }
    private func alert(_ title: String, _ text: String) {
        let a = NSAlert(); a.messageText = title; a.informativeText = text; a.addCopyButton()
        a.beginSheetModal(for: window)
    }

    private func cursorMoved(_ p: CGPoint?) {
        hRuler.cursor = p; vRuler.cursor = p
    }

    func hint(for e: Element?) {
        guard let e = e, let f = figure else { return }
        var s = e.title(label: f.labelText(e.oid))
        if e.isLabel { s += "  ·  drag moves every label, ⌥-drag this one" }
        else if e.kind == "panel" { s += "  ·  double-click for its code" }
        else if e.kind == "text" { s += "  ·  double-click to retype" }
        if let l = e.line { s += "  ·  line \(l)" }
        status.stringValue = s
    }

    private func viewChanged() {
        hRuler.needsDisplay = true; vRuler.needsDisplay = true
        updateZoomLabel()
        // sharper sprites when zoomed in far enough
        let want = canvas.wantedPxPerMM
        if want > lastPx * 1.4 || want < lastPx / 2.5 {
            lastPx = want
            NSObject.cancelPreviousPerformRequests(withTarget: self, selector: #selector(zoomRefresh), object: nil)
            perform(#selector(zoomRefresh), with: nil, afterDelay: 0.4)
        }
    }
    @objc private func zoomRefresh() { refresh() }
    private func updateZoomLabel() {
        zoomLabel.stringValue = "\(Int((canvas.scale / (72 / 25.4) * 100).rounded()))%"
    }

    // MARK: selection

    func selectionChanged() {
        navigator.selectLayers(canvas.selection)
        inspector.update()
        hRuler.needsDisplay = true; vRuler.needsDisplay = true
        showCodeOfSelection()
    }

    /// The Code tab, when it is up, shows the code of what is selected: a panel's own code (at its function, with a
    /// link to where the figure places it), the line of the figure that makes anything else, or the figure's file.
    private func showCodeOfSelection() {
        guard drawer.page == .code, !middle.isSubviewCollapsed(drawer), !code.dirty, let fig = figure else { return }
        guard let oid = canvas.selection.first, let picked = fig.element(oid) else {
            if !fig.file.isEmpty, code.path != fig.file { code.open(fig.file, line: nil) }
            return
        }
        let e = picked.isLabel ? (fig.element(picked.panelOid ?? "") ?? picked) : picked
        let place = e.file.flatMap { f in e.line.map { (f, $0) } }
        let drawsCode = e.kind == "panel" || (e.kind == "inset" && e.inner == "panel")
        if drawsCode, let f = e.codeFile, f.hasSuffix(".py") {
            code.open(f, line: e.codeLine, placedBy: place)
        } else if let (f, l) = place {
            code.open(f, line: l)
        }
    }

    func select(_ oids: [String]) {
        canvas.selection = oids.flatMap { canvas.withGroup($0) }.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
    }

    func updateInspector() { inspector.update() }

    func toolChanged() {
        toolControl.selectedSegment = Tool.allCases.firstIndex(of: canvas.tool) ?? 0
        if canvas.tool != .select { status.stringValue = "\(canvas.tool.title): " + (canvas.tool == .text ? "click where the text goes" : "drag on the figure (⌥ keeps the tool, ⇧ constrains)") }
    }
    @objc private func toolPicked() { canvas.tool = Tool.allCases[toolControl.selectedSegment]; window.makeFirstResponder(canvas) }

    // MARK: code

    func showCode(of e: Element) {
        setDrawer(visible: true)
        drawer.show(.code)
        if e.kind == "panel" || e.kind == "inset", let f = e.codeFile { code.open(f, line: e.codeLine) }
        else if let f = e.file { code.open(f, line: e.line) }
    }

    func promptText(_ title: String, _ value: String, _ done: @escaping (String) -> Void) {
        let a = NSAlert(); a.messageText = title
        let f = NSTextField(string: value); f.frame = NSRect(x: 0, y: 0, width: 240, height: 22)
        a.accessoryView = f; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { r in if r == .alertFirstButtonReturn { done(f.stringValue) } }
        DispatchQueue.main.async { a.window.makeFirstResponder(f) }
    }

    // MARK: edits on the selection

    private var sel: [String] { canvas.selection }
    private var selElements: [String] { sel.filter { !($0.hasPrefix("L")) } }

    func nudge(dx: Double, dy: Double) {
        guard !sel.isEmpty else { return }
        nudgeTotal.x += dx; nudgeTotal.y += dy
        canvas.showNudge(sel, nudgeTotal)
        nudgeWork?.cancel()
        let oids = sel
        let w = DispatchWorkItem { [weak self] in
            guard let self else { return }
            let d = self.nudgeTotal
            self.nudgeTotal = .zero
            self.edit(["op": "move", "oids": oids, "dx": d.x, "dy": d.y])
        }
        nudgeWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: w)
    }

    func order(_ how: String) { if !selElements.isEmpty { edit(["op": "order", "oids": selElements, "how": how]) } }
    func align(_ how: String, to: String? = nil) {
        guard !selElements.isEmpty else { return }
        let t = to ?? (selElements.count == 1 ? "figure" : alignTo)
        edit(["op": "align", "oids": selElements, "how": how, "to": t, "key": selElements[0]])
    }
    func distribute(_ axis: String, gap: Double? = nil) {
        var a: [String: Any] = ["op": "distribute", "oids": selElements, "axis": axis]
        if let g = gap { a["gap"] = g }
        edit(a)
    }
    func match(_ what: String) { edit(["op": "match", "oids": selElements, "what": what]) }

    @objc func deleteSelected(_ sender: Any?) { if !sel.isEmpty { let s = sel; canvas.selection = []; edit(["op": "delete", "oids": s]) } }
    @objc func delete(_ sender: Any?) { deleteSelected(sender) }
    @objc func duplicate(_ sender: Any?) { if !selElements.isEmpty { edit(["op": "duplicate", "oids": selElements, "dx": 4, "dy": 4]) } }
    /// Copy: the elements' code on the pasteboard (with the figure they came from), and their picture.
    @objc func copy(_ sender: Any?) { copySelection(then: nil) }

    private func copySelection(then: (() -> Void)?) {
        guard let name = current, !selElements.isEmpty else { return }
        let oids = selElements
        enqueue { [self] in
            do {
                let r = try await engine.json("copy", ["figure": name, "oids": oids])
                let code = r["code"] as? [String] ?? []
                let payload = try JSONSerialization.data(withJSONObject: ["figure": name, "project": project ?? "", "code": code])
                let pb = NSPasteboard.general
                pb.clearContents()
                pb.setData(payload, forType: MainController.pasteType)
                pb.setString(code.joined(separator: "\n").replacingOccurrences(of: "\u{00a7}FIG\u{00a7}.", with: "fig."), forType: .string)
                then?()
            } catch { toast(error.localizedDescription, error: true) }
        }
    }

    @objc func cut(_ sender: Any?) {
        let s = selElements
        copySelection { [weak self] in self?.canvas.selection = []; self?.edit(["op": "delete", "oids": s]) }
    }

    /// Paste: elements copied from Fignimble (into this figure, shifted 4 mm, or another one where they were), or a
    /// picture from another app, saved into images/.
    @objc func paste(_ sender: Any?) {
        guard let name = current, let f = figure else { return }
        let pb = NSPasteboard.general
        if let d = pb.data(forType: MainController.pasteType),
           let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any], let code = obj["code"] as? [String] {
            let same = obj["figure"] as? String == name && obj["project"] as? String == project
            enqueue { [self] in
                let r = (try? await engine.json("paste", ["figure": name, "code": code, "dx": same ? 4 : 0, "dy": same ? 4 : 0, "pxPerMM": lastPx])) ?? [:]
                if let fig = r["figure"] as? [String: Any] { apply(fig) }
                if let sel = r["select"] as? [String], !sel.isEmpty { canvas.selection = sel }
                if r["ok"] as? Bool != true { toast(r["error"] as? String ?? "Couldn't paste", error: true) }
                await refreshState()
            }
            return
        }
        if let img = NSImage(pasteboard: pb), let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("fignimble-paste-\(UUID().uuidString).png")
            try? png.write(to: tmp)
            let w = min(60.0, Double(f.size.width) - 10)
            enqueue { [self] in
                let r = (try? await engine.json("paste_image", ["figure": name, "path": tmp.path, "x": 5, "y": 5, "w": w, "pxPerMM": lastPx])) ?? [:]
                if let fig = r["figure"] as? [String: Any] { apply(fig) }
                if let sel = r["select"] as? [String] { canvas.selection = sel }
                if r["ok"] as? Bool != true { toast(r["error"] as? String ?? "Couldn't paste the picture", error: true) }
                await refreshState()
            }
        }
    }

    /// Copy Style (the eyedropper): the colours, line and text settings of the selected element.
    @objc func copyStyle(_ sender: Any?) {
        guard let oid = sel.first, let e = figure?.element(oid) else { return }
        let keys = ["color", "stroke", "fill", "width", "dash", "opacity", "size", "weight", "style", "font", "tip", "head", "radius", "arrow"]
        copiedStyle = e.props.filter { keys.contains($0.key) }
        toast("Copied the look of \(e.title(label: figure?.labelText(oid)))")
    }
    @objc func pasteStyle(_ sender: Any?) {
        guard let st = copiedStyle, !selElements.isEmpty else { return }
        edit(["op": "paste_style", "oids": selElements, "props": st])
    }

    func rotate(by degrees: Double) { if !selElements.isEmpty { edit(["op": "rotate", "oids": selElements, "by": degrees]) } }
    func flip(_ axis: String) { if !selElements.isEmpty { edit(["op": "flip", "oids": selElements, "axis": axis]) } }
    @objc func rotateLeft(_ sender: Any?) { rotate(by: 90) }
    @objc func rotateRight(_ sender: Any?) { rotate(by: -90) }
    @objc func flipHorizontal(_ sender: Any?) { flip("h") }
    @objc func flipVertical(_ sender: Any?) { flip("v") }
    @objc func cropPicture(_ sender: Any?) { if let oid = sel.first { canvas.beginCrop(oid) } }
    @objc func toggleLock(_ sender: Any?) {
        guard let oid = sel.first, let e = figure?.element(oid) else { return }
        edit(["op": "set", "oid": oid, "props": ["locked": !e.locked]])
    }
    @objc func toggleHide(_ sender: Any?) {
        guard let oid = sel.first, let e = figure?.element(oid) else { return }
        edit(["op": "set", "oid": oid, "props": ["hidden": !e.hidden]])
    }
    func setLayer(_ oid: String, hidden: Bool? = nil, locked: Bool? = nil) {
        var p: [String: Any] = [:]
        if let h = hidden { p["hidden"] = h }
        if let l = locked { p["locked"] = l }
        edit(["op": "set", "oid": oid, "props": p])
    }

    func replacePicture(_ oid: String) {
        let o = NSOpenPanel(); o.allowedContentTypes = [.png, .jpeg, .tiff, .pdf, .svg, .gif, .bmp, .webP]
        o.message = "The picture to show in its place (copied into the project's images folder)"
        o.beginSheetModal(for: window) { [weak self] r in
            guard r == .OK, let u = o.url else { return }
            self?.edit(["op": "replace_source", "oid": oid, "path": u.path])
        }
    }

    @objc func addScaleBar(_ sender: Any?) {
        guard let oid = sel.first, let e = figure?.element(oid), e.kind == "image" || (e.kind == "inset" && e.inner == "image") else {
            toast("Select a picture (PNG, TIFF or JPEG) for the scale bar", error: true); return
        }
        let a = NSAlert(); a.messageText = "Scale bar"
        a.informativeText = "How long the bar is, and how big one pixel of the original picture is (from the microscope's metadata)."
        let len = NSTextField(string: "50"), unit = NSTextField(string: "µm"), px = NSTextField(string: "0.325")
        for f in [len, unit, px] { f.widthAnchor.constraint(equalToConstant: 80).isActive = true }
        let grid = NSGridView(views: [[NSTextField(labelWithString: "Length"), len], [NSTextField(labelWithString: "Unit"), unit],
                                      [NSTextField(labelWithString: "One pixel is"), px]])
        grid.frame = NSRect(x: 0, y: 0, width: 220, height: 90)
        a.accessoryView = grid; a.addButton(withTitle: "Add"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { [weak self] r in
            guard r == .alertFirstButtonReturn else { return }
            self?.edit(["op": "add_scalebar", "oid": oid, "props": ["length": Double(len.stringValue) ?? 50, "unit": unit.stringValue,
                                                                     "pixel_size": Double(px.stringValue) ?? 1]])
        }
    }

    @objc func addZoom(_ sender: Any?) {
        guard !selElements.isEmpty else { toast("Select a picture (or a panel, then the one that magnifies it)", error: true); return }
        edit(["op": "add_zoom", "oids": Array(selElements.prefix(2))])
    }

    /// Undo or redo to a step of the history: `n` steps left done.
    func undoTo(_ n: Int) {
        guard let name = current else { return }
        enqueue { [self] in
            let r = (try? await engine.json("undo_to", ["n": n, "figure": name, "pxPerMM": lastPx])) ?? [:]
            if let f = r["figure"] as? [String: Any] { apply(f) }
            if r["ok"] as? Bool != true, let e = r["error"] as? String { toast(e, error: true) }
            code.reloadIfChanged()
            await refreshState()
        }
    }
    /// Recolour one mark of a panel with the colour picker; the colour is written once it settles.
    private var markColor: (oid: String, mark: PanelMark)?
    private var markColorWork: DispatchWorkItem?
    func recolorMark(_ oid: String, _ mark: PanelMark) {
        markColor = (oid, mark)
        let p = NSColorPanel.shared
        p.setTarget(nil); p.setAction(nil)
        p.color = NSColor(hex: mark.color) ?? .black
        p.setTarget(self); p.setAction(#selector(markColorChanged(_:)))
        p.makeKeyAndOrderFront(nil)
        toast("Pick a colour for \(mark.key.replacingOccurrences(of: "ax0.", with: "")) (\(mark.color))")
    }
    @objc private func markColorChanged(_ sender: NSColorPanel) {
        guard let (oid, mark) = markColor else { return }
        let c = sender.color.hex
        markColorWork?.cancel()
        let w = DispatchWorkItem { [weak self] in
            self?.edit(["op": "panel_color", "oid": oid, "keys": [mark.key], "color": c, "old": mark.color])
            self?.markColor = (oid, PanelMark(key: mark.key, color: c, box: mark.box))
        }
        markColorWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.45, execute: w)
    }

    @objc func setVision(_ sender: NSMenuItem) {
        canvas.vision = ["normal", "deuteranopia", "protanopia", "tritanopia", "greyscale"][sender.tag]
        if canvas.vision != "normal" { toast("The figure as seen with \(canvas.vision) (only on screen)") }
    }

    @objc func showHistory(_ sender: Any?) { setDrawer(visible: true); drawer.show(.history) }
    @objc func selectAll(_ sender: Any?) { canvas.selection = figure?.elements.map(\.oid) ?? [] }
    @objc func group(_ sender: Any?) { if selElements.count > 1 { edit(["op": "group", "oids": selElements]) } }
    @objc func ungroup(_ sender: Any?) { if !selElements.isEmpty { edit(["op": "ungroup", "oids": selElements]) } }
    @objc func bringToFront(_ sender: Any?) { order("front") }
    @objc func bringForward(_ sender: Any?) { order("forward") }
    @objc func sendBackward(_ sender: Any?) { order("backward") }
    @objc func sendToBack(_ sender: Any?) { order("back") }
    @objc func alignLeft(_ sender: Any?) { align("left") }
    @objc func alignCenter(_ sender: Any?) { align("hcenter") }
    @objc func alignRight(_ sender: Any?) { align("right") }
    @objc func alignTop(_ sender: Any?) { align("top") }
    @objc func alignMiddle(_ sender: Any?) { align("vcenter") }
    @objc func alignBottom(_ sender: Any?) { align("bottom") }
    @objc func distributeH(_ sender: Any?) { distribute("h") }
    @objc func distributeV(_ sender: Any?) { distribute("v") }
    @objc func matchWidth(_ sender: Any?) { match("width") }
    @objc func matchHeight(_ sender: Any?) { match("height") }
    @objc func makeLayout(_ sender: Any?) {
        let free = sel.compactMap { figure?.element($0) }.filter { ($0.kind == "panel" || $0.kind == "image") && $0.parentOid == nil }
        guard free.count >= 2 else { toast("Select two or more panels placed by hand", error: true); return }
        edit(["op": "make_layout", "oids": free.map(\.oid), "gap": 4])
    }
    func releaseLayout(_ oid: String) { edit(["op": "release_layout", "oid": oid]) }
    @objc func releaseSelectedLayout(_ sender: Any?) {
        if let oid = sel.first, let top = figure?.element(oid)?.top, figure?.element(top)?.kind == "layout" { releaseLayout(top) }
    }

    @objc func toggleDarkPreview(_ sender: Any?) {
        darkPreview.toggle()
        refresh()
        toast(darkPreview ? "Showing the figure's dark version (for talks); exports stay light unless you ask" : "Showing the figure")
    }

    @objc func setAppearance(_ sender: NSMenuItem) {
        let names = ["system", "light", "dark"]
        UserDefaults.standard.set(names[sender.tag], forKey: "appearance")
        MainController.applyAppearance()
    }
    static func applyAppearance() {
        switch UserDefaults.standard.string(forKey: "appearance") {
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        default: NSApp.appearance = nil
        }
    }

    @objc func editCode(_ sender: Any?) {
        if let oid = sel.first, let e = figure?.element(oid) { showCode(of: e) }
        else if let f = figure { setDrawer(visible: true); drawer.show(.code); code.open(f.file, line: nil) }
    }

    @objc func labelFormat(_ sender: NSMenuItem) {
        let p = Inspector.labelFormats[sender.tag]
        edit(["op": "labels", "props": ["format": p.1, "case": p.2]])
    }
    @objc func labelJournal(_ sender: NSMenuItem) {
        guard let k = sender.representedObject as? String, let lab = journals[k]?["labels"] as? [String: Any] else { return }
        edit(["op": "labels", "props": lab])
    }
    @objc func toggleLabelAlign(_ sender: Any?) {
        edit(["op": "labels", "props": ["align": !((figure?.labelStyle["align"] as? Bool) ?? true)]])
    }
    @objc func toggleLabelOrder(_ sender: Any?) {
        edit(["op": "labels", "props": ["order": (figure?.labelStyle["order"] as? String) == "source" ? "reading" : "source"]])
    }
    @objc func labelsOutside(_ sender: Any?) {
        // labels in the gutter above-left of each panel
        let size = num(figure?.labelStyle["size"] ?? 8)
        edit(["op": "labels", "props": ["dx": -(size * 0.35 + 0.5), "dy": -(size * 0.35 + 0.5)]])
    }
    @objc func labelsInside(_ sender: Any?) { edit(["op": "labels", "props": ["dx": 0, "dy": 0]]) }

    // MARK: undo

    @objc func undoEdit(_ sender: Any?) {
        if let tv = window.firstResponder as? NSTextView, tv.isEditable { tv.undoManager?.undo(); return }
        guard let name = current ?? figures.first?["name"] as? String else { return }
        enqueue { [self] in
            let r = (try? await engine.json("undo", ["figure": name, "pxPerMM": lastPx])) ?? [:]
            if let f = r["figure"] as? [String: Any] { apply(f) }
            if r["ok"] as? Bool != true, let e = r["error"] as? String { toast(e, error: true) }
            else if let l = r["label"] as? String { toast("Undid \(l)") }
            code.reloadIfChanged()
            await refreshState()
        }
    }
    @objc func redoEdit(_ sender: Any?) {
        if let tv = window.firstResponder as? NSTextView, tv.isEditable { tv.undoManager?.redo(); return }
        guard let name = current else { return }
        enqueue { [self] in
            let r = (try? await engine.json("redo", ["figure": name, "pxPerMM": lastPx])) ?? [:]
            if let f = r["figure"] as? [String: Any] { apply(f) }
            if r["ok"] as? Bool != true, let e = r["error"] as? String { toast(e, error: true) }
            code.reloadIfChanged()
            await refreshState()
        }
    }

    // MARK: files

    @objc func openProject(_ sender: Any?) {
        let p = NSOpenPanel()
        p.canChooseDirectories = true; p.canChooseFiles = true; p.allowedContentTypes = [.pythonScript, .folder]
        p.message = "Choose a Fignimble project folder (or a figure's .py file)"
        p.beginSheetModal(for: window) { [weak self] r in if r == .OK, let u = p.url { self?.openProject(at: u) } }
    }

    @objc func newProject(_ sender: Any?) {
        let p = NSSavePanel()
        p.message = "A new folder for the project's figures, panels and pictures"
        p.nameFieldStringValue = "figures"
        let journal = NSPopUpButton(frame: .zero, pullsDown: false)
        let keys = [""] + journals.keys.sorted()
        journal.addItems(withTitles: ["No journal"] + journals.keys.sorted().map { journals[$0]?["name"] as? String ?? $0 })
        if let i = keys.firstIndex(of: "nature") { journal.selectItem(at: i) }
        let acc = NSStackView(views: [NSTextField(labelWithString: "Style for:"), journal]); acc.edgeInsets = NSEdgeInsets(top: 8, left: 8, bottom: 8, right: 8)
        p.accessoryView = acc
        p.beginSheetModal(for: window) { [weak self] r in
            guard let self, r == .OK, let u = p.url else { return }
            let j = keys[journal.indexOfSelectedItem]
            Task { @MainActor in
                do {
                    var a: [String: Any] = ["dir": u.path]
                    if !j.isEmpty { a["journal"] = j }
                    _ = try await self.engine.json("new_project", a)
                    self.openProject(at: u)
                } catch { self.alert("Couldn't make the project", error.localizedDescription) }
            }
        }
    }

    @objc func newFigure(_ sender: Any?) {
        guard project != nil else { newProject(sender); return }
        let a = NSAlert(); a.messageText = "New figure"
        a.informativeText = "A figure file in the project. Sizes in mm."
        let name = NSTextField(string: "fig\(figures.count + 1)")
        let w = NSTextField(string: mm(Double(figure?.size.width ?? 183))), h = NSTextField(string: "120")
        for f in [name, w, h] { f.widthAnchor.constraint(equalToConstant: f === name ? 140 : 60).isActive = true }
        let grid = NSGridView(views: [[NSTextField(labelWithString: "Name"), name], [NSTextField(labelWithString: "Width"), w], [NSTextField(labelWithString: "Height"), h]])
        grid.frame = NSRect(x: 0, y: 0, width: 240, height: 90)
        a.accessoryView = grid; a.addButton(withTitle: "Create"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { [weak self] r in
            guard let self, r == .alertFirstButtonReturn else { return }
            self.enqueue { [weak self] in guard let self else { return }
                do {
                    let res = try await self.engine.json("new_figure", ["name": name.stringValue, "width": Double(w.stringValue) ?? 183, "height": Double(h.stringValue) ?? 120])
                    if let n = res["name"] as? String { await self.refreshState(); await self.load(n) }
                    else if let e = res["error"] as? String { self.toast(e, error: true) }
                } catch { self.toast(error.localizedDescription, error: true) }
            }
        }
    }

    @objc func newPanel(_ sender: Any?) {
        guard let name = current, let f = figure else { return }
        let a = NSAlert(); a.messageText = "New panel"
        a.informativeText = "Makes panels/<name>.py with a draw(fig) function to edit (or to ask an agent to write), and places it on the figure."
        let field = NSTextField(string: "panel"); field.frame = NSRect(x: 0, y: 0, width: 200, height: 22)
        a.accessoryView = field; a.addButton(withTitle: "Create"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { [weak self] r in
            guard let self, r == .alertFirstButtonReturn else { return }
            let stem = field.stringValue.replacingOccurrences(of: " ", with: "_")
            let c = CGPoint(x: f.size.width / 2 - 30, y: f.size.height / 2 - 22)
            self.enqueue { [weak self] in guard let self else { return }
                do {
                    let r = try await engine.json("new_panel", ["figure": name, "name": stem, "x": Double(c.x), "y": Double(c.y), "w": 60, "h": 45, "pxPerMM": lastPx])
                    if let fig = r["figure"] as? [String: Any] { apply(fig) }
                    if let sel = r["select"] as? [String] { canvas.selection = sel }
                    if let file = r["file"] as? String { setDrawer(visible: true); drawer.show(.code); await refreshState(); code.open(file, line: 1) }
                    if r["ok"] as? Bool == false { toast(r["error"] as? String ?? "", error: true) }
                } catch { toast(error.localizedDescription, error: true) }
            }
        }
    }

    @objc func insertPanelCode(_ sender: Any?) {
        guard let p = project else { return }
        let o = NSOpenPanel(); o.allowedContentTypes = [.pythonScript]; o.directoryURL = URL(fileURLWithPath: p + "/panels")
        o.message = "A Python file with a draw(fig) function"
        o.beginSheetModal(for: window) { [weak self] r in
            guard let self, r == .OK, let u = o.url, let f = self.figure else { return }
            self.importFiles([u], at: CGPoint(x: f.size.width / 2 - 30, y: f.size.height / 2 - 22))
        }
    }

    @objc func insertImage(_ sender: Any?) {
        guard figure != nil else { return }
        let o = NSOpenPanel(); o.allowsMultipleSelection = true
        o.allowedContentTypes = [.png, .jpeg, .tiff, .pdf, .svg, .gif, .bmp, .webP]
        o.message = "Pictures to place (copied into the project's images folder)"
        o.beginSheetModal(for: window) { [weak self] r in
            guard let self, r == .OK, let f = self.figure else { return }
            self.importFiles(o.urls, at: CGPoint(x: 5, y: 5 + 0 * f.size.height))
        }
    }

    func importFiles(_ urls: [URL], at p: CGPoint) {
        guard let name = current else { return }
        for (i, u) in urls.enumerated() {
            enqueue { [self] in
                do {
                    let r = try await engine.json("import_file", ["figure": name, "path": u.path, "x": Double(p.x) + Double(i) * 5, "y": Double(p.y) + Double(i) * 5, "pxPerMM": lastPx])
                    if let fig = r["figure"] as? [String: Any] { apply(fig) }
                    if let sel = r["select"] as? [String] { canvas.selection = sel }
                    if r["ok"] as? Bool == false { toast(r["error"] as? String ?? "", error: true) }
                } catch { toast(error.localizedDescription, error: true) }
                await refreshState()
            }
        }
    }

    @objc func exportFigure(_ sender: Any?) {
        guard let name = current else { return }
        let p = NSSavePanel()
        let format = NSPopUpButton(frame: .zero, pullsDown: false)
        let formats = ["pdf", "svg", "eps", "png", "tiff", "jpg"]
        format.addItems(withTitles: ["PDF (vector)", "SVG (vector)", "EPS (vector)", "PNG", "TIFF", "JPEG"])
        let dpi = NSPopUpButton(frame: .zero, pullsDown: false)
        dpi.addItems(withTitles: ["300 dpi", "600 dpi", "1200 dpi"]); dpi.selectItem(at: 1)
        let fmtAction = Action { _ in
            p.allowedContentTypes = [UTType(filenameExtension: formats[format.indexOfSelectedItem]) ?? .data]
            p.nameFieldStringValue = name + "." + formats[format.indexOfSelectedItem]
            dpi.isEnabled = format.indexOfSelectedItem >= 3
        }
        format.target = fmtAction; format.action = #selector(Action.fire(_:))
        let cmykBox = NSButton(checkboxWithTitle: "CMYK", target: nil, action: nil)
        cmykBox.toolTip = "Colours converted for print (PDF, EPS, TIFF, JPEG; PDF and EPS through Ghostscript)"
        let outlineBox = NSButton(checkboxWithTitle: "Text as outlines", target: nil, action: nil)
        outlineBox.toolTip = "Text turned into shapes, for journals that ask for it (PDF, EPS, SVG)"
        let darkBox = NSButton(checkboxWithTitle: "Dark version", target: nil, action: nil)
        darkBox.state = darkPreview ? .on : .off
        darkBox.toolTip = "White text and lines on black, for slides"
        let acc = NSStackView(views: [NSTextField(labelWithString: "Format:"), format, NSTextField(labelWithString: "Resolution:"), dpi, cmykBox, outlineBox, darkBox])
        acc.edgeInsets = NSEdgeInsets(top: 8, left: 8, bottom: 8, right: 8)
        p.accessoryView = acc
        p.nameFieldStringValue = name + ".pdf"; p.allowedContentTypes = [.pdf]; dpi.isEnabled = false
        if let proj = project { p.directoryURL = URL(fileURLWithPath: proj) }
        p.beginSheetModal(for: window) { [weak self] r in
            _ = fmtAction
            guard let self, r == .OK, let u = p.url else { return }
            let fmt = formats[format.indexOfSelectedItem], d = [300, 600, 1200][dpi.indexOfSelectedItem]
            let dark = darkBox.state == .on, cmyk = cmykBox.state == .on, outline = outlineBox.state == .on
            self.enqueue { [weak self] in guard let self else { return }
                busy("Exporting…")
                do {
                    let r = try await self.engine.json("export", ["figure": name, "path": u.path, "format": fmt, "dpi": d, "dark": dark,
                                                                          "cmyk": cmyk, "outline": outline])
                    let w = (r["warnings"] as? [String] ?? [])
                    toast("Exported \(u.lastPathComponent)" + (w.isEmpty ? "" : " (\(w.count) element\(w.count == 1 ? "" : "s") failed)"), error: !w.isEmpty)
                } catch { toast(error.localizedDescription, error: true) }
            }
        }
    }

    @objc func exportAll(_ sender: Any?) {
        guard project != nil else { return }
        let o = NSOpenPanel(); o.canChooseDirectories = true; o.canChooseFiles = false; o.canCreateDirectories = true
        o.message = "A folder for a PDF of every figure"
        o.beginSheetModal(for: window) { [weak self] r in
            guard let self, r == .OK, let dir = o.url else { return }
            let names = self.figures.compactMap { $0["name"] as? String }
            self.enqueue { [weak self] in guard let self else { return }
                busy("Exporting \(names.count) figures…")
                var failed: [String] = []
                for n in names {
                    do { _ = try await engine.json("export", ["figure": n, "path": dir.appendingPathComponent(n + ".pdf").path, "format": "pdf"]) }
                    catch { failed.append(n) }
                }
                toast(failed.isEmpty ? "Exported \(names.count) figures" : "Couldn't export \(failed.joined(separator: ", "))", error: !failed.isEmpty)
            }
        }
    }

    @objc func revealProject(_ sender: Any?) { if let p = project { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: p)]) } }
    @objc func saveCode(_ sender: Any?) { code.save() }

    // MARK: view

    @objc func zoomIn(_ sender: Any?) { canvas.zoom(by: 1.25) }
    @objc func zoomOut(_ sender: Any?) { canvas.zoom(by: 0.8) }
    @objc func zoomFit(_ sender: Any?) { canvas.fit() }
    @objc func zoomActual(_ sender: Any?) { canvas.actualSize() }
    @objc func toggleGrid(_ sender: Any?) { canvas.showGrid.toggle() }
    @objc func toggleSnapGrid(_ sender: Any?) { canvas.snapToGrid.toggle() }
    @objc func toggleSmartGuides(_ sender: Any?) { canvas.smartGuides.toggle() }
    @objc func toggleSidebar(_ sender: Any?) { navigator.isHidden.toggle() }
    @objc func toggleInspector(_ sender: Any?) { inspector.isHidden.toggle() }
    @objc func refreshFigure(_ sender: Any?) { refresh(force: true) }
    @objc func showCodePane(_ sender: Any?) {
        if !drawer.isHidden && drawer.page == .code && !middle.isSubviewCollapsed(drawer) { setDrawer(visible: false); return }
        setDrawer(visible: true); drawer.show(.code)
        showCodeOfSelection()
    }
    @objc func showProblems(_ sender: Any?) { setDrawer(visible: true); drawer.show(.problems) }

    @objc func showTerminal(_ sender: Any?) {
        if drawer.page == .terminal && !middle.isSubviewCollapsed(drawer) && sender != nil { setDrawer(visible: false); return }
        setDrawer(visible: true)
        if !terminal.hasStarted, let p = project { terminal.start(in: p, original: nil) }
        drawer.show(.terminal)
        terminal.focus()
    }
    @objc func newTerminal(_ sender: Any?) {
        guard let p = project else { return }
        setDrawer(visible: true)
        if terminal.hasStarted { terminal.addTab() } else { terminal.start(in: p, original: nil) }
        drawer.show(.terminal)
    }

    private func setDrawer(visible: Bool) {
        let collapsed = middle.isSubviewCollapsed(drawer)
        if visible && collapsed {
            middle.setPosition(middle.bounds.height - drawerHeight, ofDividerAt: 0)
        } else if !visible && !collapsed {
            drawerHeight = max(140, drawer.frame.height)
            middle.setPosition(middle.bounds.height, ofDividerAt: 0)
        }
    }

    // MARK: menus

    func contextMenu() -> NSMenu {
        let m = NSMenu()
        func item(_ t: String, _ s: Selector) { m.addItem(withTitle: t, action: s, keyEquivalent: "").target = self }
        if !sel.isEmpty {
            item("Edit Code", #selector(editCode(_:)))
            m.addItem(.separator())
            item("Bring to Front", #selector(bringToFront(_:))); item("Bring Forward", #selector(bringForward(_:)))
            item("Send Backward", #selector(sendBackward(_:))); item("Send to Back", #selector(sendToBack(_:)))
            m.addItem(.separator())
            if selElements.count > 1 { item("Group", #selector(group(_:))); item("Make Layout", #selector(makeLayout(_:))) }
            if sel.first.flatMap({ figure?.element($0)?.top }).flatMap({ figure?.element($0) })?.kind == "layout" {
                item("Release Layout", #selector(releaseSelectedLayout(_:)))
            }
            if figure.map({ f in selElements.contains { f.element($0)?.group != nil } }) == true { item("Ungroup", #selector(ungroup(_:))) }
            item("Duplicate", #selector(duplicate(_:)))
            item("Delete", #selector(deleteSelected(_:)))
        } else {
            item("New Panel…", #selector(newPanel(_:))); item("Place Picture…", #selector(insertImage(_:)))
            m.addItem(.separator())
            item("Edit the Figure's Code", #selector(editCode(_:)))
        }
        return m
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(undoEdit(_:)):
            if let tv = window.firstResponder as? NSTextView, tv.isEditable { item.title = "Undo"; return tv.undoManager?.canUndo ?? false }
            item.title = (state["undoLabel"] as? String).map { "Undo \($0)" } ?? "Undo"
            return state["canUndo"] as? Bool ?? false
        case #selector(redoEdit(_:)):
            if let tv = window.firstResponder as? NSTextView, tv.isEditable { item.title = "Redo"; return tv.undoManager?.canRedo ?? false }
            item.title = (state["redoLabel"] as? String).map { "Redo \($0)" } ?? "Redo"
            return state["canRedo"] as? Bool ?? false
        case #selector(toggleDarkPreview(_:)): item.state = darkPreview ? .on : .off; return figure != nil
        case #selector(setVision(_:)):
            item.state = canvas.vision == ["normal", "deuteranopia", "protanopia", "tritanopia", "greyscale"][item.tag] ? .on : .off
            return figure != nil
        case #selector(setAppearance(_:)):
            item.state = (UserDefaults.standard.string(forKey: "appearance") ?? "system") == ["system", "light", "dark"][item.tag] ? .on : .off
        case #selector(makeLayout(_:)):
            return sel.compactMap { figure?.element($0) }.filter { ($0.kind == "panel" || $0.kind == "image") && $0.parentOid == nil }.count >= 2
        case #selector(releaseSelectedLayout(_:)):
            return sel.first.flatMap { figure?.element($0)?.top }.flatMap { figure?.element($0) }?.kind == "layout"
        case #selector(toggleGrid(_:)): item.state = canvas.showGrid ? .on : .off
        case #selector(toggleSnapGrid(_:)): item.state = canvas.snapToGrid ? .on : .off
        case #selector(toggleSmartGuides(_:)): item.state = canvas.smartGuides ? .on : .off
        case #selector(toggleSidebar(_:)): item.title = navigator.isHidden ? "Show Figures and Layers" : "Hide Figures and Layers"
        case #selector(toggleInspector(_:)): item.title = inspector.isHidden ? "Show Inspector" : "Hide Inspector"
        case #selector(toggleLabelAlign(_:)): item.state = (figure?.labelStyle["align"] as? Bool ?? true) ? .on : .off; return figure != nil
        case #selector(toggleLabelOrder(_:)): item.state = (figure?.labelStyle["order"] as? String) == "source" ? .on : .off; return figure != nil
        case #selector(labelFormat(_:)):
            let p = Inspector.labelFormats[item.tag]
            item.state = (figure?.labelStyle["format"] as? String == p.1 && figure?.labelStyle["case"] as? String == p.2) ? .on : .off
            return figure != nil
        case #selector(deleteSelected(_:)), #selector(delete(_:)), #selector(copy(_:)), #selector(editCode(_:)):
            return !sel.isEmpty || item.action == #selector(editCode(_:)) && figure != nil
        case #selector(duplicate(_:)), #selector(bringToFront(_:)), #selector(bringForward(_:)), #selector(sendBackward(_:)), #selector(sendToBack(_:)),
             #selector(alignLeft(_:)), #selector(alignCenter(_:)), #selector(alignRight(_:)), #selector(alignTop(_:)), #selector(alignMiddle(_:)), #selector(alignBottom(_:)),
             #selector(ungroup(_:)):
            return !selElements.isEmpty
        case #selector(group(_:)), #selector(matchWidth(_:)), #selector(matchHeight(_:)), #selector(distributeH(_:)), #selector(distributeV(_:)):
            return selElements.count > 1
        case #selector(paste(_:)):
            let pb = NSPasteboard.general
            return figure != nil && (pb.data(forType: MainController.pasteType) != nil || NSImage.canInit(with: pb))
        case #selector(cut(_:)), #selector(copyStyle(_:)): return !selElements.isEmpty
        case #selector(pasteStyle(_:)): return copiedStyle != nil && !selElements.isEmpty
        case #selector(rotateLeft(_:)), #selector(rotateRight(_:)), #selector(toggleLock(_:)), #selector(toggleHide(_:)):
            return !selElements.isEmpty
        case #selector(flipHorizontal(_:)), #selector(flipVertical(_:)), #selector(cropPicture(_:)), #selector(addScaleBar(_:)):
            return sel.first.flatMap { figure?.element($0) }.map { $0.kind == "image" || ($0.kind == "inset" && $0.inner == "image") } ?? false
        case #selector(addZoom(_:)): return !selElements.isEmpty
        case #selector(selectAll(_:)): return figure != nil
        case #selector(newPanel(_:)), #selector(insertImage(_:)), #selector(insertPanelCode(_:)), #selector(exportFigure(_:)),
             #selector(labelsOutside(_:)), #selector(labelsInside(_:)), #selector(labelJournal(_:)), #selector(refreshFigure(_:)):
            return figure != nil
        case #selector(newFigure(_:)), #selector(exportAll(_:)), #selector(revealProject(_:)), #selector(showTerminal(_:)), #selector(newTerminal(_:)):
            return project != nil
        case #selector(saveCode(_:)): return code.dirty
        default: break
        }
        return true
    }

    // MARK: window

    func windowShouldClose(_ sender: NSWindow) -> Bool { confirmClose() }

    func confirmClose() -> Bool {
        if code.dirty {
            let a = NSAlert(); a.messageText = "Apply your unsaved code changes first?"
            a.addButton(withTitle: "Apply"); a.addButton(withTitle: "Discard"); a.addButton(withTitle: "Cancel")
            switch a.runModal() {
            case .alertFirstButtonReturn: code.save()
            case .alertSecondButtonReturn: break
            default: return false
            }
        }
        let running = terminal.runningCommands
        if !running.isEmpty {
            let a = NSAlert(); a.messageText = "Stop \(running.joined(separator: ", ")) in the terminal?"
            a.informativeText = "Closing Fignimble ends the terminals."
            a.addButton(withTitle: "Close"); a.addButton(withTitle: "Cancel")
            if a.runModal() != .alertFirstButtonReturn { return false }
        }
        return true
    }

    func windowWillClose(_ n: Notification) { finish(); NSApp.terminate(nil) }

    func finish() {
        terminal.terminateAll()
        // the engine removes the agent instruction files it wrote into the project when its input ends
        engine.finishInput()
        let deadline = Date().addingTimeInterval(2)
        while engine.isRunning && Date() < deadline { usleep(50_000) }
        engine.stop()
    }
}
