import AppKit

/// The first-launch setup: runs setup_python.sh (Contents/Resources) in a sheet with its steps, the download's
/// progress and the end of its output, which can be canceled. `done(true)` once the Python is in place.
@MainActor
final class PythonSetup: NSObject {
    private let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 480, height: 230), styleMask: [.titled], backing: .buffered, defer: false)
    private let stepLabel = NSTextField(labelWithString: "Starting…")
    private let bar = NSProgressIndicator()
    private let log = NSTextField(wrappingLabelWithString: "")
    private let cancelButton = NSButton(title: "Cancel", target: nil, action: nil)
    private var process: Process?
    private var buffer = ""
    private var tail: [String] = []
    private var canceled = false
    private var keep: PythonSetup?
    private var done: ((Bool) -> Void)?

    static func run(over window: NSWindow, done: @escaping (Bool) -> Void) {
        let s = PythonSetup()
        s.keep = s
        s.done = done
        s.begin(over: window)
    }

    /// Where the Python goes, and where Engine.findPython looks for it.
    static var support: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Fignimble")
    }
    static var python: String { support.appendingPathComponent("python/bin/python").path }

    static var script: String? {
        if let r = Bundle.main.resourcePath, FileManager.default.fileExists(atPath: r + "/setup_python.sh") { return r + "/setup_python.sh" }
        // running from a checkout (apps/macos/Fignimble.app)
        let s = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("setup_python.sh").path
        return FileManager.default.fileExists(atPath: s) ? s : nil
    }

    private func begin(over window: NSWindow) {
        let title = NSTextField(labelWithString: "Setting up Python for Fignimble")
        title.font = Theme.font(13, .semibold)
        stepLabel.font = Theme.font(12)
        bar.style = .bar; bar.isIndeterminate = true; bar.minValue = 0; bar.maxValue = 100
        bar.startAnimation(nil)
        log.font = Theme.mono(10); log.textColor = .secondaryLabelColor; log.preferredMaxLayoutWidth = 440
        log.maximumNumberOfLines = 4; log.lineBreakMode = .byTruncatingHead
        cancelButton.target = self; cancelButton.action = #selector(cancel)
        let buttons = NSStackView(views: [NSView(), cancelButton])
        let stack = NSStackView(views: [title, stepLabel, bar, log, buttons])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
        stack.edgeInsets = NSEdgeInsets(top: 16, left: 18, bottom: 14, right: 18)
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = NSView(); panel.contentView = content
        content.addSubview(stack)
        for v in [bar, log, buttons] { v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -36).isActive = true }
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor), stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor), stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            content.widthAnchor.constraint(equalToConstant: 480),
        ])
        window.makeKeyAndOrderFront(nil)
        window.beginSheet(panel)
        guard let script = PythonSetup.script else { finish(false, "The setup script is missing from the app."); return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [script]
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        env["FIGNIMBLE_SUPPORT"] = PythonSetup.support.path
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe; p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty else { return }
            let s = String(decoding: d, as: UTF8.self)
            Task { @MainActor in self?.read(s) }
        }
        p.terminationHandler = { [weak self] p in
            let ok = p.terminationStatus == 0
            Task { @MainActor in
                pipe.fileHandleForReading.readabilityHandler = nil
                self?.finish(ok, nil)
            }
        }
        process = p
        do { try p.run() } catch { finish(false, "Couldn't run the setup: \(error.localizedDescription)") }
    }

    /// Steps ("@@ …"), curl's "NN.N%" progress (it redraws with carriage returns) and the rest as the log's tail.
    private func read(_ s: String) {
        buffer += s
        let parts = buffer.components(separatedBy: CharacterSet(charactersIn: "\r\n"))
        buffer = parts.last ?? ""
        for line in parts.dropLast() + [buffer] where !line.isEmpty {
            if line.hasPrefix("@@ ") {
                stepLabel.stringValue = String(line.dropFirst(3)) + "…"
                bar.isIndeterminate = true; bar.startAnimation(nil)
            } else if let r = line.range(of: #"([0-9]+(\.[0-9])?)%\s*$"#, options: .regularExpression),
                      let v = Double(line[r].dropLast().trimmingCharacters(in: .whitespaces)) {
                bar.isIndeterminate = false; bar.doubleValue = v
            } else if line != buffer {
                tail.append(line); tail = Array(tail.suffix(4))
                log.stringValue = tail.joined(separator: "\n")
            }
        }
    }

    @objc private func cancel() {
        canceled = true
        process?.terminate()
    }

    private func finish(_ ok: Bool, _ why: String?) {
        guard let done else { return }
        self.done = nil
        bar.stopAnimation(nil)
        panel.sheetParent?.endSheet(panel)
        if !ok && !canceled {
            let a = NSAlert()
            a.messageText = "Python couldn't be set up"
            a.informativeText = (why ?? (tail + [buffer]).filter { !$0.isEmpty }.suffix(6).joined(separator: "\n"))
                + "\n\nCheck the internet connection and try again."
            a.addCopyButton()
            a.runModal()
        }
        Engine.note(ok ? "python set up" : (canceled ? "python setup canceled" : "python setup failed: \(tail.last ?? why ?? "")"))
        done(ok)
        keep = nil
    }
}
