import AppKit

/// The code behind the figure: the figure file, its style and its panels' files, editable. Saving (⌘S) goes
/// through the engine, so it is one undo step like a canvas edit; a file changed on disk (by an agent) is reloaded
/// unless it has unsaved edits here.
final class CodePane: NSView, NSTextViewDelegate {
    weak var main: MainController?
    private let files = NSPopUpButton(frame: .zero, pullsDown: false)
    private let status = NSTextField(labelWithString: "")
    let actions = NSStackView()
    private(set) var path: String?
    private var loaded = ""                 // the file's text when loaded or saved
    private var loadedDate: Date?
    private var highlighting = false
    var dirty: Bool { path != nil && textView.string != loaded }
    private let pathLabel = NSTextField(labelWithString: "")
    private let placedButton = NSButton(title: "", target: nil, action: nil)
    private let editorButton = NSButton(title: "Open in Editor", target: nil, action: nil)
    /// Where the panel shown here is placed on the figure (file, line), for the header's link.
    private var placedBy: (String, Int)?

    override init(frame: NSRect) {
        super.init(frame: frame)
        let scroll = NSTextView.scrollableTextView()
        let tv = scroll.documentView as! NSTextView
        tv.font = Theme.mono(12); tv.isRichText = false; tv.allowsUndo = true
        tv.isAutomaticQuoteSubstitutionEnabled = false; tv.isAutomaticDashSubstitutionEnabled = false
        tv.isAutomaticTextReplacementEnabled = false; tv.isAutomaticSpellingCorrectionEnabled = false
        tv.isContinuousSpellCheckingEnabled = false; tv.smartInsertDeleteEnabled = false
        tv.textContainerInset = NSSize(width: 8, height: 8); tv.delegate = self
        tv.drawsBackground = true
        Theme.layerColors(self) { v in tv.backgroundColor = Theme.codeBackground; tv.textColor = .labelColor; tv.insertionPointColor = .labelColor }
        tv.isHorizontallyResizable = true; tv.textContainer?.widthTracksTextView = false
        tv.textContainer?.containerSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude)
        scroll.hasHorizontalScroller = true
        textView = tv
        files.controlSize = .small; files.font = Theme.font(11); files.target = self; files.action = #selector(pickFile)
        status.font = Theme.font(10); status.textColor = Theme.ink(0.45)
        for v in [files, status, barButton("square.and.arrow.down", "Save (⌘S): apply to the figure", self, #selector(save)),
                  barButton("arrow.uturn.backward", "Revert to the file on disk", self, #selector(revert))] as [NSView] {
            actions.addArrangedSubview(v)
        }
        actions.spacing = 10; actions.alignment = .centerY
        // the header: which file this is, where it lives, and ways to open it elsewhere
        let header = NSView(); header.wantsLayer = true
        Theme.layerColors(header) { $0.layer?.backgroundColor = Theme.codeBackground.cgColor }
        pathLabel.font = Theme.mono(10.5); pathLabel.textColor = Theme.ink(0.6)
        pathLabel.lineBreakMode = .byTruncatingMiddle; pathLabel.isSelectable = true
        pathLabel.setContentCompressionResistancePriority(.init(100), for: .horizontal)
        placedButton.setContentCompressionResistancePriority(.init(150), for: .horizontal)
        pathLabel.toolTip = "Where this file is. Every edit in Fignimble is saved to it straight away."
        placedButton.bezelStyle = .inline; placedButton.controlSize = .small; placedButton.font = Theme.font(10.5)
        placedButton.target = self; placedButton.action = #selector(goToPlacement); placedButton.isHidden = true
        placedButton.toolTip = "Show the line of the figure file that places this panel"
        editorButton.bezelStyle = .inline; editorButton.controlSize = .small; editorButton.font = Theme.font(10.5)
        editorButton.target = self; editorButton.action = #selector(openInEditor)
        let finder = NSButton(title: "Show in Finder", target: self, action: #selector(showInFinder))
        finder.bezelStyle = .inline; finder.controlSize = .small; finder.font = Theme.font(10.5)
        let doc = NSImageView(image: NSImage(systemSymbolName: "doc.text", accessibilityDescription: nil) ?? NSImage())
        doc.contentTintColor = Theme.ink(0.45)
        let spacer = NSView(); spacer.setContentHuggingPriority(.init(1), for: .horizontal)
        let bar = NSStackView(views: [doc, pathLabel, placedButton, spacer, finder, editorButton])
        bar.spacing = 8; bar.alignment = .centerY
        bar.translatesAutoresizingMaskIntoConstraints = false
        header.addSubview(bar)
        let line = hairline()
        for v in [header, line, scroll] as [NSView] { v.translatesAutoresizingMaskIntoConstraints = false; addSubview(v) }
        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: leadingAnchor), header.trailingAnchor.constraint(equalTo: trailingAnchor),
            header.topAnchor.constraint(equalTo: topAnchor), header.heightAnchor.constraint(equalToConstant: 24),
            bar.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 10), bar.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -10),
            bar.centerYAnchor.constraint(equalTo: header.centerYAnchor),
            line.leadingAnchor.constraint(equalTo: leadingAnchor), line.trailingAnchor.constraint(equalTo: trailingAnchor),
            line.topAnchor.constraint(equalTo: header.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: leadingAnchor), scroll.trailingAnchor.constraint(equalTo: trailingAnchor),
            scroll.topAnchor.constraint(equalTo: line.bottomAnchor), scroll.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])
        updateEditorButton()
    }
    required init?(coder: NSCoder) { fatalError() }
    private(set) var textView: NSTextView!

    /// The files offered: the figure, the style, and the panel files the project has.
    func setFiles(_ list: [String]) {
        let cur = path
        files.removeAllItems()
        for p in list { files.addItem(withTitle: relative(p)); files.lastItem?.representedObject = p }
        if let c = cur, let i = list.firstIndex(of: c) { files.selectItem(at: i) }
    }

    /// Another project is opening: show nothing of this one (its file, its edits, their undo) until a file of the new
    /// one is opened.
    func clear() {
        path = nil; loaded = ""; loadedDate = nil; placedBy = nil
        textView.string = ""
        textView.undoManager?.removeAllActions()
        files.removeAllItems()
        updateStatus(); updateHeader()
    }

    private func relative(_ p: String) -> String {
        guard let root = main?.project else { return (p as NSString).lastPathComponent }
        return p.hasPrefix(root + "/") ? String(p.dropFirst(root.count + 1)) : (p as NSString).lastPathComponent
    }

    @objc private func pickFile() {
        guard let p = files.selectedItem?.representedObject as? String else { return }
        open(p, line: nil)
    }

    /// Show a file (saving nothing: unsaved edits of another file are kept only if the user says so).
    func open(_ p: String, line: Int?, placedBy place: (String, Int)? = nil) {
        placedBy = place
        if p != path, dirty {
            let a = NSAlert(); a.messageText = "Save your changes to \(relative(path!))?"
            a.addButton(withTitle: "Save"); a.addButton(withTitle: "Don't Save"); a.addButton(withTitle: "Cancel")
            switch a.runModal() {
            case .alertFirstButtonReturn: save()
            case .alertSecondButtonReturn: break
            default: return
            }
        }
        if p != path || !dirty { if p != path || loaded.isEmpty { load(p) } }
        if let i = (files.itemArray.firstIndex { $0.representedObject as? String == p }) { files.selectItem(at: i) }
        else { files.addItem(withTitle: relative(p)); files.lastItem?.representedObject = p; files.select(files.lastItem) }
        if let l = line { reveal(line: l) }
        updateHeader()
    }

    private func updateHeader() {
        pathLabel.stringValue = path.map { ($0 as NSString).abbreviatingWithTildeInPath } ?? ""
        if let (f, l) = placedBy, f != path {
            placedButton.title = "placed by \((f as NSString).lastPathComponent), line \(l) ›"
            placedButton.isHidden = false
        } else { placedButton.isHidden = true }
    }

    @objc private func goToPlacement() {
        guard let (f, l) = placedBy else { return }
        open(f, line: l)
    }

    @objc private func showInFinder() {
        if let p = path { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: p)]) }
    }

    /// A code editor for .py files: the one chosen before, else a known editor that is installed, else the system's
    /// choice (unless that would run the file, as Python Launcher does), else TextEdit.
    private static func editorApp() -> URL? {
        let ws = NSWorkspace.shared
        if let saved = UserDefaults.standard.string(forKey: "codeEditor"), let u = ws.urlForApplication(withBundleIdentifier: saved) { return u }
        for id in ["com.microsoft.VSCode", "com.todesktop.230313mzl4w4u92", "com.barebones.bbedit", "dev.zed.Zed",
                   "com.sublimetext.4", "com.panic.Nova", "com.jetbrains.pycharm", "com.jetbrains.pycharm.ce"] {
            if let u = ws.urlForApplication(withBundleIdentifier: id) { return u }
        }
        if let u = ws.urlForApplication(toOpen: URL(fileURLWithPath: "/tmp/x.py")),
           Bundle(url: u)?.bundleIdentifier != "org.python.PythonLauncher" { return u }
        return ws.urlForApplication(withBundleIdentifier: "com.apple.TextEdit")
    }

    private func updateEditorButton() {
        let name = CodePane.editorApp().map { FileManager.default.displayName(atPath: $0.path).replacingOccurrences(of: ".app", with: "") } ?? "Editor"
        editorButton.title = "Open in \(name)"
        editorButton.toolTip = "Open this file in \(name). Fignimble notices its saves and redraws the figure. (⌥-click to choose another editor)"
    }

    @objc private func openInEditor() {
        guard let p = path else { return }
        if NSEvent.modifierFlags.contains(.option) {
            let o = NSOpenPanel(); o.directoryURL = URL(fileURLWithPath: "/Applications"); o.allowedContentTypes = [.application]
            o.message = "The editor to open Fignimble's code files in"
            guard o.runModal() == .OK, let u = o.url, let id = Bundle(url: u)?.bundleIdentifier else { return }
            UserDefaults.standard.set(id, forKey: "codeEditor")
            updateEditorButton()
        }
        if dirty { save() }
        guard let app = CodePane.editorApp() else { NSWorkspace.shared.open(URL(fileURLWithPath: p)); return }
        NSWorkspace.shared.open([URL(fileURLWithPath: p)], withApplicationAt: app, configuration: NSWorkspace.OpenConfiguration())
    }

    private func load(_ p: String) {
        let s = (try? String(contentsOfFile: p, encoding: .utf8)) ?? ""
        path = p; loaded = s
        loadedDate = (try? FileManager.default.attributesOfItem(atPath: p)[.modificationDate]) as? Date
        let sel = textView.selectedRange()
        textView.string = s
        textView.setSelectedRange(NSRange(location: min(sel.location, (s as NSString).length), length: 0))
        highlight()
        updateStatus()
    }

    /// The file changed on disk: reload it unless it has unsaved edits here.
    func reloadIfChanged() {
        guard let p = path, !dirty else { return }
        let d = (try? FileManager.default.attributesOfItem(atPath: p)[.modificationDate]) as? Date
        if d != loadedDate { load(p) }
    }

    func reveal(line: Int) {
        let ns = textView.string as NSString
        var loc = 0, n = 1
        while n < line, loc < ns.length { loc = NSMaxRange(ns.lineRange(for: NSRange(location: loc, length: 0))); n += 1 }
        let r = ns.lineRange(for: NSRange(location: min(loc, ns.length), length: 0))
        textView.scrollRangeToVisible(r)
        textView.setSelectedRange(NSRange(location: r.location, length: 0))
        textView.showFindIndicator(for: NSRange(location: r.location, length: max(0, r.length - 1)))
    }

    @objc func save() {
        guard let p = path, dirty else { return }
        let t = textView.string
        loaded = t
        updateStatus()
        main?.writeSource(p, t) { [weak self] in
            self?.loadedDate = (try? FileManager.default.attributesOfItem(atPath: p)[.modificationDate]) as? Date
        }
    }

    @objc private func revert() { if let p = path { load(p) } }

    func textDidChange(_ n: Notification) { highlight(); updateStatus() }

    private func updateStatus() { status.stringValue = dirty ? "edited · ⌘S to apply" : "" }

    // MARK: Python coloring

    private static let keywords = Set("False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield".split(separator: " ").map(String.init))
    private static let fignimble = Set("Figure Labels Style panel image text line arrow rect ellipse bracket guide".split(separator: " ").map(String.init))

    private func highlight() {
        guard !highlighting, let storage = textView.textStorage else { return }
        highlighting = true; defer { highlighting = false }
        let s = storage.string as NSString
        let all = NSRange(location: 0, length: s.length)
        storage.beginEditing()
        storage.setAttributes([.font: Theme.mono(12), .foregroundColor: NSColor.labelColor], range: all)
        let kw = Theme.dynamic(light: NSColor(srgbRed: 0.61, green: 0.14, blue: 0.58, alpha: 1), dark: NSColor(srgbRed: 0.99, green: 0.45, blue: 0.75, alpha: 1))
        let str = Theme.dynamic(light: NSColor(srgbRed: 0.77, green: 0.10, blue: 0.09, alpha: 1), dark: NSColor(srgbRed: 0.99, green: 0.55, blue: 0.45, alpha: 1))
        let numc = Theme.dynamic(light: NSColor(srgbRed: 0.11, green: 0.0, blue: 0.81, alpha: 1), dark: NSColor(srgbRed: 0.82, green: 0.75, blue: 0.5, alpha: 1))
        let com = Theme.ink(0.42)
        let fig = Theme.accent
        func color(_ pattern: String, _ c: NSColor, group: Int = 0) {
            guard let re = try? NSRegularExpression(pattern: pattern, options: [.anchorsMatchLines]) else { return }
            for m in re.matches(in: storage.string, range: all) { storage.addAttribute(.foregroundColor, value: c, range: m.range(at: group)) }
        }
        color("\\b[0-9]+(\\.[0-9]+)?\\b", numc)
        color("\\b[A-Za-z_][A-Za-z0-9_]*\\b", .labelColor)
        if let re = try? NSRegularExpression(pattern: "\\b[A-Za-z_][A-Za-z0-9_]*\\b") {
            for m in re.matches(in: storage.string, range: all) {
                let w = s.substring(with: m.range)
                if CodePane.keywords.contains(w) { storage.addAttribute(.foregroundColor, value: kw, range: m.range) }
                else if CodePane.fignimble.contains(w) { storage.addAttribute(.foregroundColor, value: fig, range: m.range) }
            }
        }
        color("(\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?'''|\"(\\\\.|[^\"\\\\\\n])*\"|'(\\\\.|[^'\\\\\\n])*')", str)
        color("#[^\\n]*$", com)
        storage.endEditing()
    }
}
